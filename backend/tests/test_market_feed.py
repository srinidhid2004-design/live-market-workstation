import asyncio
import json
import sqlite3
import unittest
from collections.abc import Callable
from contextlib import asynccontextmanager, closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from typing import Literal
from unittest.mock import patch

import httpx

from app.main import create_app
from app.market_feed import FeedUnavailable
from app.observations import UNIX_EPOCH, Observation, ObservationStore


OPEN = datetime(2026, 11, 9, 14, 30, tzinfo=UTC)
FIRST = "2026-11-09T14:30:00Z"
SECOND = "2026-11-09T14:31:00Z"
MARKET_FIELDS = {"timestamp", "open", "high", "low", "close", "volume"}
CONTEXT_FIELDS = {
    "version", "type", "symbol", "interval", "source", "data_mode", "feed_status",
    "source_time", "latest_source_time", "receipt_time", "age_seconds", "as_of",
    "observation_id", "backend_status",
}


class Clock:
    def __init__(self) -> None:
        self.value = OPEN

    def __call__(self) -> datetime:
        return self.value


class FakeFeed:
    source_name = "constructed_test"
    cumulative_volume_field = None

    def __init__(self, mode: Literal["recorded", "live"] = "recorded") -> None:
        self.data_mode = mode
        self.events: asyncio.Queue[Observation | FeedUnavailable] = asyncio.Queue()
        self.opened = asyncio.Event()
        self.closed = asyncio.Event()
        self.subscriptions = 0

    async def observations(self):
        self.subscriptions += 1
        self.opened.set()
        try:
            while True:
                event = await self.events.get()
                try:
                    yield event
                finally:
                    self.events.task_done()
        finally:
            self.closed.set()

    async def send(self, event: Observation | FeedUnavailable) -> None:
        await self.events.put(event)
        await asyncio.wait_for(self.events.join(), timeout=3)


class BrowserSocket:
    """A bounded ASGI peer that uses no listener or network socket."""

    def __init__(self, app, query: str) -> None:
        self.incoming: asyncio.Queue[dict] = asyncio.Queue()
        self.outgoing: asyncio.Queue[dict] = asyncio.Queue()
        self.on_message: Callable[[dict], None] | None = None
        self.incoming.put_nowait({"type": "websocket.connect"})
        path = "/api/market-feed"
        self.task = asyncio.create_task(app({
            "type": "websocket",
            "asgi": {"version": "3.0", "spec_version": "2.4"},
            "scheme": "ws",
            "path": path,
            "raw_path": path.encode(),
            "root_path": "",
            "query_string": query.encode(),
            "headers": [(b"host", b"testserver")],
            "subprotocols": [],
            "client": ("testclient", 12345),
            "server": ("testserver", 80),
        }, self.incoming.get, self._send))

    async def _send(self, event: dict) -> None:
        if self.on_message is not None and event["type"] == "websocket.send":
            self.on_message(json.loads(event["text"]))
        await self.outgoing.put(event)

    async def receive(self) -> dict:
        return await asyncio.wait_for(self.outgoing.get(), timeout=3)

    async def message(self, kind: str | None = None, *, status: str | None = None) -> dict:
        async with asyncio.timeout(3):
            while True:
                event = await self.outgoing.get()
                if event["type"] != "websocket.send":
                    raise AssertionError(f"Expected a JSON WebSocket message, received {event['type']}.")
                data = json.loads(event["text"])
                if (kind is None or data["type"] == kind) and (status is None or data["feed_status"] == status):
                    return data

    def drain(self) -> list[dict]:
        messages = []
        while not self.outgoing.empty():
            event = self.outgoing.get_nowait()
            if event["type"] != "websocket.send":
                raise AssertionError(f"Expected a JSON WebSocket message, received {event['type']}.")
            messages.append(json.loads(event["text"]))
        return messages

    async def disconnect(self) -> None:
        if not self.task.done():
            await self.incoming.put({"type": "websocket.disconnect", "code": 1000})
        await asyncio.wait_for(self.task, timeout=3)


@asynccontextmanager
async def browser(app, query: str = "symbol=AAPL&interval=1m"):
    peer = BrowserSocket(app, query)
    try:
        yield peer
    finally:
        await peer.disconnect()


class MarketFeedTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        workspace = Path(__file__).resolve().parents[1]
        self.folder = Path(self.enterContext(TemporaryDirectory(dir=workspace)))
        self.database = self.folder / "constructed.sqlite3"
        self.clock = Clock()
        self.feed = FakeFeed()

    def create_app(self):
        return create_app(provider=self.feed, database_path=self.database, clock=self.clock)

    def observation(self, source_seconds: int, price: float, event_id: str | None = None) -> Observation:
        stamp = OPEN + timedelta(seconds=source_seconds)
        return Observation(
            source_name=self.feed.source_name,
            ticker="AAPL",
            source_timestamp=int((stamp - UNIX_EPOCH).total_seconds()),
            source_timestamp_unit="s",
            received_at=self.clock(),
            price=price,
            verified_event_id=event_id,
        )

    async def seed(self) -> None:
        self.clock.value = OPEN + timedelta(seconds=10)
        await self.feed.send(self.observation(5, 100))

    async def snapshot(self, peer: BrowserSocket) -> dict:
        self.assertEqual((await peer.receive())["type"], "websocket.accept")
        snapshot = await peer.message()
        self.assertEqual(snapshot["type"], "snapshot")
        return snapshot

    def assert_context(self, message: dict, interval: str) -> None:
        self.assertLessEqual(CONTEXT_FIELDS, message.keys())
        self.assertEqual((message["version"], message["symbol"], message["interval"]), (1, "AAPL", interval))
        self.assertEqual(message["source"], self.feed.source_name)
        self.assertEqual(message["data_mode"], self.feed.data_mode)

    async def history(self, app, interval: str = "1m") -> dict:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            response = await client.get("/api/history", params={"symbol": "AAPL", "interval": interval})
        self.assertEqual(response.status_code, 200)
        return response.json()

    async def test_snapshot_matches_selected_http_history(self) -> None:
        app = self.create_app()
        self.assertFalse(self.feed.opened.is_set())
        self.assertFalse(self.database.exists())
        async with app.router.lifespan_context(app):
            await self.seed()
            for interval in ("1m", "5m", "15m", "1h", "1d"):
                with self.subTest(interval=interval):
                    expected = await self.history(app, interval)
                    self.assertEqual((expected["source"], expected["data_mode"]), (self.feed.source_name, "recorded"))
                    async with browser(app, f"symbol=AAPL&interval={interval}") as peer:
                        snapshot = await self.snapshot(peer)
                        self.assert_context(snapshot, interval)
                        self.assertEqual(snapshot["feed_status"], "recorded")
                        self.assertEqual(snapshot["candles"], expected["candles"])
                        self.assertEqual(snapshot["metadata"], expected["metadata"])
                        self.assertEqual(snapshot["as_of"], expected["as_of"])
                        self.assertEqual(len(snapshot["candles"]), 1)
                        self.assertEqual(set(snapshot["candles"][0]), MARKET_FIELDS)
                        self.assertIsNone(snapshot["candles"][0]["volume"])

    async def test_default_synthetic_mode_opens_no_database(self) -> None:
        self.clock.value = OPEN + timedelta(hours=1)
        app = create_app(database_path=self.database, clock=self.clock)
        async with app.router.lifespan_context(app):
            expected = await self.history(app)
            async with browser(app) as peer:
                snapshot = await self.snapshot(peer)
                self.assertEqual(snapshot["candles"], expected["candles"])
                self.assertEqual(snapshot["metadata"], expected["metadata"])
                self.assertEqual(len(snapshot["candles"]), 3)
                self.assertEqual(snapshot["data_mode"], "synthetic")
                self.assertEqual(snapshot["feed_status"], "unavailable")
                self.assertEqual(snapshot["backend_status"], "connected")
        self.assertFalse(self.database.exists())

    async def test_out_of_calendar_observation_keeps_valid_candles_available(self) -> None:
        app = self.create_app()
        async with app.router.lifespan_context(app):
            await self.seed()
            unsupported_time = (datetime(1999, 1, 4, 14, 30, tzinfo=UTC) - OPEN) // timedelta(seconds=1)
            async with browser(app) as peer:
                await self.snapshot(peer)
                await self.feed.send(self.observation(unsupported_time, 999))
                status = await peer.message("feed_status")
                self.assertEqual(status["observation_id"], 2)
                self.assertEqual([row.price for row in ObservationStore(self.database).read()], [100, 999])
                history = await self.history(app)
                self.assertEqual([(row["timestamp"], row["close"]) for row in history["candles"]], [(FIRST, 100)])

    async def test_same_next_and_late_observations_upsert_by_timestamp(self) -> None:
        app = self.create_app()
        async with app.router.lifespan_context(app):
            await self.seed()
            async with browser(app) as peer:
                snapshot = await self.snapshot(peer)
                self.assertEqual(snapshot["candles"][0]["timestamp"], FIRST)
                self.assertFalse(snapshot["metadata"][0]["is_complete"])

                self.clock.value = OPEN + timedelta(seconds=25)
                await self.feed.send(self.observation(20, 103))
                same = await peer.message("candle_upsert")
                self.assert_context(same, "1m")
                self.assertEqual(same["candle"], {
                    "timestamp": FIRST, "open": 100, "high": 103, "low": 100, "close": 103, "volume": None,
                })
                self.assertFalse(same["metadata"]["is_complete"])
                self.assertEqual(len((await self.history(app))["candles"]), 1)

                self.clock.value = OPEN + timedelta(seconds=75)
                await self.feed.send(self.observation(70, 104))
                while (next_message := await peer.message("candle_upsert"))["candle"]["timestamp"] != SECOND:
                    self.assertEqual(next_message["candle"]["timestamp"], FIRST)
                self.assertEqual(next_message["candle"]["close"], 104)
                self.assertEqual([candle["timestamp"] for candle in (await self.history(app))["candles"]], [FIRST, SECOND])

                self.clock.value = OPEN + timedelta(seconds=85)
                await self.feed.send(self.observation(12, 98))
                late = await peer.message("candle_upsert")
                self.assertEqual(late["candle"]["timestamp"], FIRST)
                self.assertEqual((late["candle"]["low"], late["candle"]["close"]), (98, 103))
                self.assertTrue(late["metadata"]["is_complete"])
                self.assertIsNone(late["candle"]["volume"])
                self.assertEqual(datetime.fromisoformat(late["source_time"]), OPEN + timedelta(seconds=12))
                self.assertEqual(datetime.fromisoformat(late["latest_source_time"]), OPEN + timedelta(seconds=70))
                self.assertEqual(datetime.fromisoformat(late["receipt_time"]), self.clock())
                self.assertEqual(late["age_seconds"], 15)

    async def test_correction_exists_in_sqlite_before_publication_and_repeat_is_suppressed(self) -> None:
        app = self.create_app()
        async with app.router.lifespan_context(app):
            self.clock.value = OPEN + timedelta(seconds=10)
            initial = self.observation(5, 100, "constructed-event")
            await self.feed.send(initial)
            async with browser(app) as peer:
                await self.snapshot(peer)
                published_ids = []

                def check_commit_at_send(message: dict) -> None:
                    if message["type"] == "candle_upsert":
                        with closing(sqlite3.connect(self.database, timeout=0)) as connection:
                            rows = connection.execute(
                                "SELECT observation_id, revision_of, price FROM observations ORDER BY observation_id"
                            ).fetchall()
                        self.assertEqual(len(rows), 2)
                        self.assertEqual(rows[1], (message["observation_id"], rows[0][0], 105))
                        published_ids.append(message["observation_id"])

                peer.on_message = check_commit_at_send
                corrected = self.observation(5, 105, "constructed-event")
                await self.feed.send(corrected)
                event = await peer.message("candle_upsert")
                self.assertEqual((event["candle"]["open"], event["candle"]["close"]), (105, 105))
                await self.feed.send(corrected)
                await self.feed.send(initial)
                await app.state.market_feed.refresh()
                self.assertEqual(len(ObservationStore(self.database).read()), 2)
                self.assertEqual(len((await self.history(app))["candles"]), 1)
                self.assertEqual(published_ids, [event["observation_id"]])
                self.assertFalse(any(message["type"] == "candle_upsert" for message in peer.drain()))

    async def test_revision_moving_between_intervals_replaces_snapshot(self) -> None:
        app = self.create_app()
        async with app.router.lifespan_context(app):
            self.clock.value = OPEN + timedelta(seconds=10)
            await self.feed.send(self.observation(5, 100, "constructed-event"))
            async with browser(app) as peer:
                initial = await self.snapshot(peer)
                self.assertEqual([row["timestamp"] for row in initial["candles"]], [FIRST])
                self.clock.value = OPEN + timedelta(seconds=75)
                await self.feed.send(self.observation(70, 105, "constructed-event"))
                updated = await peer.message("snapshot")
                self.assertEqual([row["timestamp"] for row in updated["candles"]], [SECOND])
                self.assertEqual(updated["candles"][0]["close"], 105)
                self.assertEqual([row["timestamp"] for row in (await self.history(app))["candles"]], [SECOND])

    async def test_shared_provider_and_browser_disconnect_are_independent(self) -> None:
        app = self.create_app()
        async with app.router.lifespan_context(app):
            await asyncio.wait_for(self.feed.opened.wait(), timeout=3)
            async with browser(app) as one, browser(app, "symbol=AAPL&interval=5m") as two:
                await self.snapshot(one)
                await self.snapshot(two)
                self.assertEqual(self.feed.subscriptions, 1)
                self.assertEqual(app.state.market_feed.client_count, 2)
                await self.seed()
                for peer, interval in ((one, "1m"), (two, "5m")):
                    event = await peer.message("candle_upsert")
                    self.assert_context(event, interval)
                    self.assertEqual(event["feed_status"], "recorded")
                await one.disconnect()
                self.assertFalse(self.feed.closed.is_set())
                self.assertEqual(app.state.market_feed.client_count, 1)
                self.clock.value = OPEN + timedelta(seconds=20)
                await self.feed.send(self.observation(15, 101))
                event = await two.message("candle_upsert")
                self.assertEqual(event["feed_status"], "recorded")
                self.assertEqual(event["candle"]["close"], 101)
                self.assertEqual(self.feed.subscriptions, 1)

    async def test_upstream_failure_and_recovery_leave_browser_connected(self) -> None:
        app = self.create_app()
        async with app.router.lifespan_context(app):
            await self.seed()
            async with browser(app) as peer:
                await self.snapshot(peer)
                await self.feed.send(FeedUnavailable())
                status = await peer.message("feed_status", status="unavailable")
                self.assertEqual(status["feed_status"], "unavailable")
                self.assertEqual(status["backend_status"], "connected")
                self.assertFalse(peer.task.done())
                self.clock.value = OPEN + timedelta(seconds=20)
                await self.feed.send(self.observation(15, 101))
                event = await peer.message("candle_upsert")
                self.assertEqual(event["feed_status"], "recorded")
                self.assertEqual(event["backend_status"], "connected")
                self.assertEqual(event["candle"]["close"], 101)

    async def test_injected_clock_updates_age_staleness_and_completion(self) -> None:
        self.feed = FakeFeed("live")
        app = self.create_app()
        async with app.router.lifespan_context(app):
            async with browser(app) as peer:
                initial = await self.snapshot(peer)
                self.assertEqual(initial["feed_status"], "connecting")
                self.assertIsNone(initial["age_seconds"])
                await self.seed()
                event = await peer.message("candle_upsert")
                self.assertEqual((event["feed_status"], event["age_seconds"]), ("live", 5))

                self.clock.value = OPEN + timedelta(seconds=126)
                await app.state.market_feed.refresh()
                stale_seen = complete_seen = False
                async with asyncio.timeout(3):
                    while not (stale_seen and complete_seen):
                        update = await peer.message()
                        if update["feed_status"] == "stale":
                            self.assertEqual(update["age_seconds"], 121)
                            stale_seen = True
                        if update["type"] == "candle_upsert" and update["candle"]["timestamp"] == FIRST:
                            complete_seen = update["metadata"]["is_complete"]
                        if update["type"] == "snapshot":
                            complete_seen = any(
                                row["timestamp"] == FIRST and row["is_complete"] for row in update["metadata"]
                            )
                refreshed = await self.history(app)
                self.assertTrue(refreshed["metadata"][0]["is_complete"])

                await self.feed.send(self.observation(125, 102))
                event = await peer.message("candle_upsert")
                self.assertEqual((event["feed_status"], event["age_seconds"]), ("live", 1))

    async def test_invalid_queries_receive_safe_error_and_close(self) -> None:
        app = self.create_app()
        async with app.router.lifespan_context(app):
            for query in ("symbol=UNTRUSTED&interval=1m", "symbol=AAPL&interval=2m", "symbol=AAPL&interval=1m&interval=5m"):
                with self.subTest(query=query):
                    async with browser(app, query) as peer:
                        self.assertEqual((await peer.receive())["type"], "websocket.accept")
                        error = await peer.message("error")
                        self.assertIn("code", error)
                        self.assertIn("message", error)
                        self.assertNotIn("candles", error)
                        self.assertNotIn("UNTRUSTED", json.dumps(error))
                        self.assertEqual((await peer.receive())["type"], "websocket.close")
            self.assertEqual(app.state.market_feed.client_count, 0)

    async def test_shutdown_closes_upstream_and_client_and_releases_database(self) -> None:
        app = self.create_app()
        peer = None
        try:
            async with app.router.lifespan_context(app):
                await self.seed()
                peer = BrowserSocket(app, "symbol=AAPL&interval=1m")
                await self.snapshot(peer)
                self.assertTrue(self.database.exists())
                self.assertFalse(self.feed.closed.is_set())
            async with asyncio.timeout(3):
                while (event := await peer.outgoing.get())["type"] != "websocket.close":
                    self.assertEqual(event["type"], "websocket.send")
            await asyncio.wait_for(peer.task, timeout=3)
            self.assertTrue(self.feed.closed.is_set())
            self.assertEqual(app.state.market_feed.client_count, 0)
            self.database.unlink()
            self.assertFalse(any(self.folder.iterdir()))
        finally:
            if peer is not None:
                await peer.disconnect()

    async def test_shutdown_joins_snapshot_read_after_socket_deadline(self) -> None:
        app = self.create_app()
        async with app.router.lifespan_context(app):
            await self.seed()
            feed = app.state.market_feed
            original_history = feed._history
            loop = asyncio.get_running_loop()
            read_started = asyncio.Event()
            release_read = Event()
            read_finished = Event()

            def slow_history(interval, as_of):
                loop.call_soon_threadsafe(read_started.set)
                try:
                    if not release_read.wait(timeout=3):
                        raise AssertionError("Snapshot read was never released.")
                    return original_history(interval, as_of)
                finally:
                    read_finished.set()

            with patch.object(feed, "_history", slow_history), patch("app.main.SEND_SECONDS", 0.2):
                try:
                    async with browser(app) as peer:
                        self.assertEqual((await peer.receive())["type"], "websocket.accept")
                        await asyncio.wait_for(read_started.wait(), timeout=1)
                        error = await peer.message("error")
                        self.assertEqual(error["code"], "history_unavailable")
                        self.assertEqual((await peer.receive())["type"], "websocket.close")
                        self.assertFalse(read_finished.is_set())
                    shutdown = asyncio.create_task(feed.stop())
                    done, _ = await asyncio.wait({shutdown}, timeout=0.05)
                    self.assertFalse(done)
                finally:
                    release_read.set()
                await asyncio.wait_for(shutdown, timeout=1)
                self.assertTrue(read_finished.is_set())
