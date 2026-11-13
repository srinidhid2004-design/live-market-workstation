"""Serve bounded, server-paced replay from a read-only archive."""

import asyncio
import json
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from re import Pattern
from typing import Literal, cast

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from starlette.datastructures import QueryParams
from starlette.websockets import WebSocketState

from .replay import ReplayArchive, ReplayCursor, ReplaySelectionError, ReplayUnavailable
from .timeframes import INTERVAL_MINUTES, HistoryResponse, Interval, utc_text


SPEEDS = (1, 2, 4)
MAX_RECEIPT_GAP_SECONDS = 2.0
MAX_CONNECTIONS = 4
MAX_COMMANDS = 4096
MAX_COMMAND_LENGTH = 128
MAX_QUERY_BYTES = 1024
IO_SECONDS = 5
SESSION_SECONDS = 45 * 60

ReplayState = Literal["ready", "playing", "paused", "completed", "empty", "failed"]
ReplayAction = Literal["play", "pause", "reset"]


@dataclass(frozen=True)
class Selection:
    source: str
    symbol: str
    start: str
    end: str
    interval: Interval
    speed: int


def _selection(query: QueryParams, utc_pattern: Pattern[str]) -> Selection:
    values = dict(query)
    if len(values) != len(query.multi_items()) or values.keys() != {"source", "symbol", "start", "end", "interval", "speed"}:
        raise ReplaySelectionError("Invalid replay selection.")
    source, symbol = values["source"], values["symbol"]
    start, end = values["start"], values["end"]
    interval, speed = values["interval"], values["speed"]
    if (not 1 <= len(source) <= 64 or not 1 <= len(symbol) <= 16
            or not utc_pattern.fullmatch(start) or not utc_pattern.fullmatch(end)
            or interval not in INTERVAL_MINUTES or speed not in {"1", "2", "4"}):
        raise ReplaySelectionError("Invalid replay selection.")
    try:
        datetime.fromisoformat(start)
        datetime.fromisoformat(end)
    except ValueError:
        raise ReplaySelectionError("Invalid replay selection.") from None
    return Selection(source, symbol, start, end, cast(Interval, interval), int(speed))


def replay_delay(recorded_seconds: float, speed: int) -> float:
    """Convert an original receipt gap to a bounded wall-clock wait."""
    return min(MAX_RECEIPT_GAP_SECONDS, max(0.0, recorded_seconds)) / speed


def _command(raw: str | None) -> tuple[ReplayAction, int | None]:
    if raw is None or len(raw) > MAX_COMMAND_LENGTH:
        raise ValueError
    data = json.loads(raw)
    if not isinstance(data, dict) or data.get("action") not in ("play", "pause", "reset"):
        raise ValueError
    action = data["action"]
    speed = data.get("speed")
    if data.keys() == {"action"}:
        return action, None
    if action != "play" or data.keys() != {"action", "speed"} or type(speed) is not int or speed not in SPEEDS:
        raise ValueError
    return action, speed


async def _worker[**P, T](work: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
    # Keep the worker owned by this request even if the socket times out or closes.
    task = asyncio.create_task(asyncio.to_thread(work, *args, **kwargs))
    try:
        return await asyncio.wait_for(asyncio.shield(task), IO_SECONDS)
    finally:
        await asyncio.gather(task, return_exceptions=True)


def _context(
    selection: Selection | None, state: ReplayState, cursor: ReplayCursor | None,
    speed: int | None = None,
) -> dict[str, object]:
    observation = cursor.observation if cursor else None
    return {
        "version": 1, "data_mode": "replay", "feed_status": "off", "backend_status": "connected",
        "replay_state": state, "source": selection.source if selection else None,
        "symbol": selection.symbol if selection else None, "interval": selection.interval if selection else None,
        "start": selection.start if selection else None, "end": selection.end if selection else None,
        "speed": speed if speed is not None else (selection.speed if selection else None),
        "position": cursor.position if cursor else 0, "count": cursor.count if cursor else 0,
        "as_of": utc_text(cursor.evaluated_at) if cursor else None,
        "volume_unit": cursor.volume_unit if cursor else None,
        "observation_id": observation.observation_id if observation else None,
        "source_time": observation.source_time_utc if observation else None,
        "receipt_time": observation.receipt_time_utc if observation else None,
        "source_timestamp": observation.source_timestamp if observation else None,
        "source_timestamp_unit": observation.source_timestamp_unit if observation else None,
        "verified_event_id": observation.verified_event_id if observation else None,
        "revision_of": observation.revision_of if observation else None,
        "volume_fields": observation.volume_fields if observation else None,
    }


async def _send(socket: WebSocket, data: dict[str, object]) -> None:
    await asyncio.wait_for(socket.send_json(data), IO_SECONDS)


async def _close(socket: WebSocket, code: int) -> None:
    if socket.application_state == WebSocketState.CONNECTED and socket.client_state == WebSocketState.CONNECTED:
        with suppress(TimeoutError, WebSocketDisconnect, OSError):
            await asyncio.wait_for(socket.close(code=code), IO_SECONDS)


async def _fail(
    socket: WebSocket, selection: Selection | None, code: str, message: str, close_code: int,
) -> None:
    if socket.application_state == WebSocketState.CONNECTED and socket.client_state == WebSocketState.CONNECTED:
        with suppress(TimeoutError, WebSocketDisconnect, OSError):
            await _send(socket, {**_context(selection, "failed", None), "type": "error", "code": code, "message": message})
        await _close(socket, close_code)


async def _playback(socket: WebSocket, selection: Selection, cursor: ReplayCursor) -> None:
    speed = selection.speed
    state: ReplayState = "ready"

    async def status(message: str | None = None) -> None:
        await _send(socket, {**_context(selection, state, cursor, speed), "type": "replay_status", "message": message})

    async def snapshot(history: HistoryResponse) -> None:
        await _send(socket, {
            **_context(selection, state, cursor, speed), "type": "snapshot",
            "candles": history["candles"], "metadata": history["metadata"],
        })

    if not cursor.count:
        state = "empty"
        await status("No recorded observations exist for this selection.")
        await _close(socket, 1000)
        return

    await status()
    clock = asyncio.get_running_loop().time
    commands = 0
    deadline: float | None = None
    remaining = 0.0  # Capped recorded seconds, independent of the current speed.
    incoming = asyncio.create_task(socket.receive())
    try:
        while True:
            timeout = None if deadline is None else max(0.0, deadline - clock())
            await asyncio.wait({incoming}, timeout=timeout)
            if not incoming.done():
                await snapshot(await _worker(cursor.advance))
                if cursor.next_delay is None:
                    state = "completed"
                    deadline = None
                    await snapshot(await _worker(cursor.complete))
                else:
                    deadline = clock() + replay_delay(cursor.next_delay, speed)
                continue

            event = incoming.result()
            if event["type"] == "websocket.disconnect":
                return
            commands += 1
            try:
                if commands > MAX_COMMANDS:
                    raise ValueError
                action, new_speed = _command(event.get("text"))
            except ValueError:
                await _fail(socket, selection, "invalid_command", "Invalid replay command.", 1008)
                return
            incoming = asyncio.create_task(socket.receive())
            if action == "reset":
                state = "ready"
                deadline = None
                remaining = 0.0
                await snapshot(cursor.reset())
            elif action == "pause" and state == "playing":
                assert deadline is not None
                remaining = max(0.0, deadline - clock()) * speed
                deadline = None
                state = "paused"
                await status()
            elif action == "play" and state != "completed":
                if deadline is not None:
                    remaining = max(0.0, deadline - clock()) * speed
                speed = new_speed or speed
                state = "playing"
                deadline = clock() + remaining / speed
                await status()
    finally:
        incoming.cancel()
        await asyncio.gather(incoming, return_exceptions=True)


def replay_router(
    archive: ReplayArchive, *, enabled: bool, allowed_origins: frozenset[str], utc_pattern: Pattern[str],
) -> APIRouter:
    router = APIRouter(prefix="/api/replay")
    connections = 0

    @router.get("/coverage")
    async def coverage() -> dict[str, object]:
        if not enabled:
            return {"available": False, "recordings": []}
        try:
            return {"available": True, "recordings": await _worker(archive.coverage)}
        except (ReplayUnavailable, TimeoutError):
            raise HTTPException(503, "Recorded sessions are unavailable.") from None

    @router.websocket("/stream")
    async def stream(socket: WebSocket) -> None:
        nonlocal connections
        origin = socket.headers.get("origin")
        if origin is not None and origin not in allowed_origins:
            await socket.close(code=1008)
            return
        await socket.accept()
        selection = None
        reserved = False
        try:
            if not enabled:
                await _fail(socket, None, "replay_disabled", "Restart the backend with its upstream feed off to replay.", 1008)
                return
            if connections >= MAX_CONNECTIONS:
                await _fail(socket, None, "replay_busy", "Replay is busy. Try again later.", 1013)
                return
            connections += 1
            reserved = True
            async with asyncio.timeout(SESSION_SECONDS):
                if len(socket.scope.get("query_string", b"")) > MAX_QUERY_BYTES:
                    raise ReplaySelectionError("Invalid replay selection.")
                selection = _selection(socket.query_params, utc_pattern)
                cursor = await _worker(
                    archive.load, selection.source, selection.symbol, datetime.fromisoformat(selection.start),
                    datetime.fromisoformat(selection.end), selection.interval,
                )
                await _playback(socket, selection, cursor)
        except (WebSocketDisconnect, OSError):
            pass
        except ReplaySelectionError as exc:
            await _fail(socket, selection, "invalid_selection", str(exc), 1008)
        except Exception:
            await _fail(socket, selection, "replay_unavailable", "Replay is unavailable. Try again.", 1011)
        finally:
            if reserved:
                connections -= 1

    return router
