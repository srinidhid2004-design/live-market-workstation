import asyncio
import re
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import NotRequired, cast

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from starlette.datastructures import QueryParams

from .candles import MINUTE
from .history import load_candles
from .market_feed import DataMode, MarketFeed, ObservationProvider
from .observations import DEFAULT_DATABASE, ObservationStore
from .timeframes import INTERVAL_MINUTES, SYMBOL, HistoryResponse, Interval, aggregate_minutes, session_calendar


HISTORY_FILE = Path(__file__).resolve().parents[1] / "data" / "sample-candles.csv"
UTC_TIME = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?(?:Z|\+00:00)")
SEND_SECONDS = 5


class MarketHistoryResponse(HistoryResponse):
    source: NotRequired[str]
    data_mode: NotRequired[DataMode]


def utc_now() -> datetime:
    return datetime.now(UTC)


def _evaluation_time(as_of: str | None, now: datetime) -> datetime:
    if as_of is None:
        return now
    error = HTTPException(status_code=422, detail="as_of must be a supported UTC timestamp at or before now.")
    if not UTC_TIME.fullmatch(as_of):
        raise error
    try:
        value = datetime.fromisoformat(as_of)
    except ValueError:
        raise error from None
    calendar = session_calendar()
    if value > now or not calendar.first_session.date() <= value.date() <= calendar.last_session.date():
        raise error
    return value


def _query_error(query: QueryParams, allowed: set[str], symbol: str, interval: str) -> str | None:
    keys = [key for key, _ in query.multi_items()]
    if len(keys) != len(set(keys)) or any(key not in allowed for key in keys):
        return "Invalid history query parameters."
    if symbol != SYMBOL:
        return "Unsupported symbol."
    if interval not in INTERVAL_MINUTES:
        return "Unsupported interval."
    return None


def synthetic_history(interval: Interval, as_of: datetime) -> HistoryResponse:
    available = (
        row for row in load_candles(HISTORY_FILE)
        if as_of - datetime.fromisoformat(row["timestamp"]) >= MINUTE
    )
    return aggregate_minutes(available, interval=interval, as_of=as_of)


def create_app(
    *, provider: ObservationProvider | None = None,
    database_path: Path = DEFAULT_DATABASE,
    clock: Callable[[], datetime] = utc_now,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI):
        store = await asyncio.to_thread(ObservationStore, database_path) if provider is not None else None
        feed = MarketFeed(provider=provider, store=store, clock=clock, synthetic_history=synthetic_history)
        application.state.market_feed = feed
        await feed.start()
        try:
            yield
        finally:
            await feed.stop()

    application = FastAPI(title="Live Market Workstation", lifespan=lifespan)

    @application.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "healthy"}

    @application.get("/api/history")
    async def history(
        request: Request, symbol: str = SYMBOL, interval: str = "1m", as_of: str | None = None,
    ) -> MarketHistoryResponse:
        error = _query_error(request.query_params, {"symbol", "interval", "as_of"}, symbol, interval)
        if error:
            raise HTTPException(status_code=422, detail=error)
        evaluated_at = _evaluation_time(as_of, clock())
        selection = cast(Interval, interval)
        try:
            if provider is None:
                return cast(MarketHistoryResponse, await asyncio.to_thread(synthetic_history, selection, evaluated_at))
            feed: MarketFeed = request.app.state.market_feed
            result = await feed.history(selection, evaluated_at)
            return {**result, "source": feed.source, "data_mode": feed.data_mode}
        except Exception:
            raise HTTPException(status_code=500, detail="Historical candle data is unavailable.") from None

    @application.websocket("/api/market-feed")
    async def market_feed(socket: WebSocket) -> None:
        feed: MarketFeed = socket.app.state.market_feed
        query = socket.query_params
        symbol, interval = query.get("symbol", SYMBOL), query.get("interval", "1m")
        selection = cast(Interval, interval) if interval in INTERVAL_MINUTES else None
        origin = socket.headers.get("origin")
        if origin is not None and origin not in {
            "http://127.0.0.1:5173", "http://localhost:5173",
            "http://127.0.0.1:8000", "http://localhost:8000",
        }:
            await socket.close(code=1008)
            return
        await socket.accept()

        async def reject(code: str, message: str, close_code: int) -> None:
            await asyncio.wait_for(socket.send_json({
                **feed.context(selection, clock()), "type": "error", "code": code, "message": message,
            }), SEND_SECONDS)
            await asyncio.wait_for(socket.close(code=close_code), SEND_SECONDS)

        client = None
        tasks: set[asyncio.Task] = set()
        try:
            error = _query_error(query, {"symbol", "interval"}, symbol, interval)
            if error or selection is None:
                await reject("invalid_subscription", "Unsupported market feed selection.", 1008)
                return
            try:
                client = await asyncio.wait_for(feed.subscribe(selection), SEND_SECONDS)
            except Exception:
                await reject("history_unavailable", "Market history is unavailable.", 1011)
                return
            if client is None:
                await reject("feed_busy", "Market feed is busy.", 1013)
                return

            incoming = asyncio.create_task(socket.receive())
            outgoing = asyncio.create_task(client.queue.get())
            tasks.update((incoming, outgoing))
            while True:
                done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                if incoming in done:
                    if incoming.result()["type"] != "websocket.disconnect":
                        await reject("read_only", "Market feed sockets are read-only.", 1008)
                    return
                messages = outgoing.result()
                if messages is None:
                    await asyncio.wait_for(socket.close(code=1001), SEND_SECONDS)
                    return
                for message in messages:
                    await asyncio.wait_for(socket.send_json(message), SEND_SECONDS)
                tasks.remove(outgoing)
                outgoing = asyncio.create_task(client.queue.get())
                tasks.add(outgoing)
        except (WebSocketDisconnect, OSError):
            pass
        except TimeoutError:
            try:
                await asyncio.wait_for(socket.close(code=1013), SEND_SECONDS)
            except (TimeoutError, WebSocketDisconnect, OSError):
                pass
        finally:
            if client is not None:
                feed.unsubscribe(client)
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    return application


def create_live_app() -> FastAPI:
    """Opt in to one Yahoo subscription through Uvicorn's application lifecycle."""
    from .yahoo_observations import YahooObservationSource

    return create_app(provider=YahooObservationSource())


app = create_app()
