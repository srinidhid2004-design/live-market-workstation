import asyncio
import json
import sqlite3
import unittest
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch
from urllib.parse import urlencode

import httpx

from app.main import create_app
from app.observations import UNIX_EPOCH, Observation, ObservationStore
from app.replay import ReplayArchive, ReplayUnavailable
from app.replay_routes import replay_delay
from tests.replay_fixture import fixture_evidence, seed_replay_fixture
from tests.test_market_feed import BrowserSocket, FakeFeed


START = "2026-11-09T14:30:00Z"
END = "2026-11-09T14:32:00Z"
NEXT_MINUTE = "2026-11-09T14:31:00Z"
FIXTURE_SOURCE = "constructed_test"
VOLUME_FIELDS = {FIXTURE_SOURCE: "day_volume"}


def query(**options: str) -> str:
    return urlencode({
        "source": FIXTURE_SOURCE, "symbol": "AAPL", "start": START, "end": END,
        "interval": "1m", "speed": "4", **options,
    })


def command(peer: BrowserSocket, action: str, **fields: object) -> None:
    peer.incoming.put_nowait({"type": "websocket.receive", "text": json.dumps({"action": action, **fields})})


async def state(peer: BrowserSocket, expected: str) -> dict:
    async with asyncio.timeout(4):
        while True:
            message = await peer.message()
            if message["replay_state"] == expected:
                return message


class ReplayTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        workspace = Path(__file__).resolve().parents[1]
        folder = Path(self.enterContext(TemporaryDirectory(dir=workspace)))
        self.database = folder / "constructed.sqlite3"
        self.missing = folder / "missing.sqlite3"
        seed_replay_fixture(self.database)

    def app(self, database: Path | None = None):
        return create_app(database_path=database or self.database, replay_cumulative_fields=VOLUME_FIELDS)

    async def coverage(self, app) -> dict:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            response = await client.get("/api/replay/coverage")
        self.assertEqual(response.status_code, 200)
        return response.json()

    async def connect(self, app, selection: str | None = None) -> BrowserSocket:
        peer = BrowserSocket(app, selection or query(), path="/api/replay/stream")
        self.addAsyncCleanup(peer.disconnect)
        self.assertEqual((await peer.receive())["type"], "websocket.accept")
        return peer

    async def replay_run(self, peer: BrowserSocket, speed: int) -> tuple[list[dict], dict]:
        command(peer, "play", speed=speed)
        await state(peer, "playing")
        frames = [await peer.message("snapshot") for _ in range(5)]
        completed = await state(peer, "completed")
        return frames, completed

    async def test_coverage_and_selection_bounds(self) -> None:
        app = self.app()
        async with app.router.lifespan_context(app):
            coverage = await self.coverage(app)
            self.assertIs(coverage["available"], True)
            self.assertEqual([(row["source"], row["symbol"], row["count"]) for row in coverage["recordings"]], [
                (FIXTURE_SOURCE, "AAPL", 6),
            ])
            for selection in (
                query(start="invalid"), query(start=END), query(end="2026-11-11T14:32:00Z"),
                query(speed="8"), query(interval="10m"), query(symbol="A" * 100), query() + "&speed=1",
            ):
                with self.subTest(selection=selection):
                    peer = await self.connect(app, selection)
                    failure = await peer.message("error")
                    self.assertEqual(failure["replay_state"], "failed")
                    self.assertNotIn(str(self.database), json.dumps(failure))
                    self.assertEqual((await peer.receive())["type"], "websocket.close")

    async def test_empty_selection_and_absent_database_do_not_write(self) -> None:
        before = self.database.read_bytes()
        for database in (self.database, self.missing):
            app = self.app(database)
            async with app.router.lifespan_context(app):
                if database == self.missing:
                    self.assertEqual((await self.coverage(app))["recordings"], [])
                peer = await self.connect(app, query(start="2026-11-09T15:30:00Z", end="2026-11-09T15:32:00Z"))
                message = await state(peer, "empty")
                self.assertEqual(message["data_mode"], "replay")
                self.assertEqual(message["feed_status"], "off")
                await peer.disconnect()
        self.assertEqual(self.database.read_bytes(), before)
        self.assertFalse(self.missing.exists())

    async def test_replay_is_disabled_while_a_provider_is_configured(self) -> None:
        provider = FakeFeed("live")
        app = create_app(provider=provider, database_path=self.database)
        async with app.router.lifespan_context(app):
            await asyncio.wait_for(provider.opened.wait(), timeout=3)
            self.assertIs((await self.coverage(app))["available"], False)
            peer = await self.connect(app)
            self.assertEqual((await peer.message("error"))["replay_state"], "failed")
            self.assertEqual((await peer.receive())["type"], "websocket.close")
        self.assertEqual(provider.subscriptions, 1)

    async def test_replays_the_same_receipt_prefixes_twice_read_only(self) -> None:
        before = fixture_evidence(self.database)
        app = self.app()
        with (
            patch("app.yahoo_observations.YahooObservationSource.observations", new_callable=AsyncMock) as yahoo,
            patch("app.observations.ObservationStore.record", side_effect=AssertionError("Unexpected replay write.")),
        ):
            async with app.router.lifespan_context(app):
                peer = await self.connect(app)
                ready = await state(peer, "ready")
                self.assertEqual((ready["data_mode"], ready["feed_status"], ready["position"]), ("replay", "off", 0))
                self.assertIsNone(ready["observation_id"])
                first, completed = await self.replay_run(peer, 4)
                command(peer, "reset")
                reset = await state(peer, "ready")
                self.assertEqual((reset["position"], reset["candles"]), (0, []))
                second, completed_again = await self.replay_run(peer, 2)
                await peer.disconnect()
            yahoo.assert_not_called()

        self.assertEqual([frame["observation_id"] for frame in first], [2, 3, 4, 5, 6])
        self.assertEqual([frame["position"] for frame in first], [1, 2, 3, 4, 5])
        self.assertTrue(all(frame["volume_unit"] == "shares" for frame in first))
        self.assertEqual([frame["candles"][0]["close"] for frame in first], [100, 100, 109, 98, 105])
        self.assertEqual([frame["candles"][0]["high"] for frame in first], [100, 100, 109, 109, 105])
        self.assertEqual([frame["candles"][0]["low"] for frame in first], [100, 100, 100, 98, 98])
        self.assertEqual([frame["metadata"][0]["is_complete"] for frame in first], [False, True, True, True, True])
        self.assertEqual(first[2]["source_time"], "2026-11-09T14:30:40.000000Z")
        self.assertEqual(first[2]["receipt_time"], "2026-11-09T14:31:07.000000Z")
        self.assertEqual(first[2]["verified_event_id"], "replay-late")
        self.assertIsNone(first[3]["verified_event_id"])
        self.assertEqual(first[4]["revision_of"], 4)
        self.assertEqual(first[4]["volume_fields"], {"day_volume": 1000})
        final = first[-1]["candles"]
        self.assertEqual((final[0]["close"], final[0]["volume"]), (before["close"], before["volume"]))
        self.assertEqual(final, [
            {"timestamp": START, "open": 100, "high": 105, "low": 98, "close": 105, "volume": 0},
            {"timestamp": NEXT_MINUTE, "open": 110, "high": 110, "low": 110, "close": 110, "volume": None},
        ])
        for one, two in zip(first, second, strict=True):
            self.assertEqual({**one, "speed": 2}, two)
        self.assertEqual({**completed, "speed": 2}, completed_again)
        self.assertEqual(completed["candles"], final)
        self.assertTrue(all(row["is_complete"] for row in completed["metadata"]))
        self.assertEqual(fixture_evidence(self.database), before)

    async def test_pause_stops_emission_and_resume_continues(self) -> None:
        app = self.app()
        async with app.router.lifespan_context(app):
            peer = await self.connect(app)
            await state(peer, "ready")
            command(peer, "play", speed=1)
            await state(peer, "playing")
            self.assertEqual((await peer.message("snapshot"))["observation_id"], 2)
            command(peer, "pause")
            paused = await state(peer, "paused")
            self.assertEqual((paused["position"], paused["observation_id"]), (1, 2))
            with self.assertRaises(TimeoutError):
                await asyncio.wait_for(peer.outgoing.get(), timeout=0.15)
            command(peer, "play", speed=4)
            await state(peer, "playing")
            self.assertEqual((await peer.message("snapshot"))["observation_id"], 3)
            await peer.disconnect()

    async def test_invalid_command_fails_safely(self) -> None:
        app = self.app()
        async with app.router.lifespan_context(app):
            peer = await self.connect(app)
            await state(peer, "ready")
            command(peer, "play", speed=1.5)
            failure = await peer.message("error")
            self.assertEqual((failure["replay_state"], failure["code"]), ("failed", "invalid_command"))
            self.assertEqual((await peer.receive())["code"], 1008)

    async def test_archive_without_a_verified_volume_mapping_keeps_volume_unknown(self) -> None:
        app = create_app(database_path=self.database)
        async with app.router.lifespan_context(app):
            peer = await self.connect(app)
            await state(peer, "ready")
            command(peer, "play", speed=4)
            await state(peer, "playing")
            frame = await peer.message("snapshot")
            self.assertIsNone(frame["volume_unit"])
            self.assertIsNone(frame["candles"][0]["volume"])
            self.assertEqual(frame["volume_fields"], {"day_volume": 1000})
            await peer.disconnect()

    def test_speed_changes_wall_clock_delay_without_changing_receipt_gap(self) -> None:
        self.assertEqual([replay_delay(0.8, speed) for speed in (1, 2, 4)], [0.8, 0.4, 0.2])
        self.assertEqual(replay_delay(59, 4), 0.5)
        self.assertEqual(replay_delay(-1, 1), 0)

    def test_replay_connection_enforces_query_only_and_read_only_uri(self) -> None:
        before = self.database.read_bytes()
        with ReplayArchive(self.database).connect() as connection:
            self.assertEqual(connection.execute("PRAGMA query_only").fetchone()[0], 1)
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 1)
            with self.assertRaises(sqlite3.OperationalError):
                connection.execute("UPDATE observations SET price = 101 WHERE observation_id = 2")
            connection.execute("PRAGMA query_only = OFF")
            with self.assertRaises(sqlite3.OperationalError):
                connection.execute("UPDATE observations SET price = 101 WHERE observation_id = 2")
        self.assertEqual(self.database.read_bytes(), before)

    def test_wal_database_is_refused_without_creating_sidecars(self) -> None:
        with closing(sqlite3.connect(self.database)) as connection:
            self.assertEqual(connection.execute("PRAGMA journal_mode = WAL").fetchone()[0], "wal")
        before = self.database.read_bytes()
        files = set(self.database.parent.iterdir())
        with self.assertRaises(ReplayUnavailable):
            ReplayArchive(self.database).coverage()
        self.assertEqual(self.database.read_bytes(), before)
        self.assertEqual(set(self.database.parent.iterdir()), files)

    def test_higher_timeframe_uses_exchange_buckets_and_retains_unknown_volume(self) -> None:
        cursor = ReplayArchive(self.database, cumulative_fields=VOLUME_FIELDS).load(
            FIXTURE_SOURCE, "AAPL", datetime.fromisoformat(START), datetime.fromisoformat(END), "5m",
        )
        for _ in range(cursor.count):
            cursor.advance()
        frame = cursor.complete()
        self.assertEqual(frame["candles"], [
            {"timestamp": START, "open": 100, "high": 110, "low": 98, "close": 110, "volume": None},
        ])
        self.assertEqual(frame["metadata"], [
            {"timestamp": START, "observed_minutes": 2, "expected_minutes": 5, "coverage": "partial", "is_complete": False},
        ])

    def test_equal_and_backward_receipt_times_use_ids_and_a_monotonic_clock(self) -> None:
        start = datetime.fromisoformat(START)
        store = ObservationStore(self.missing)
        for source, receipt, price in [(5, 10, 100), (6, 10, 101), (7, 9, 102), (8, 11, 103)]:
            store.record(Observation(
                source_name=FIXTURE_SOURCE, ticker="AAPL",
                source_timestamp=(start - UNIX_EPOCH) // timedelta(seconds=1) + source,
                source_timestamp_unit="s", received_at=start + timedelta(seconds=receipt), price=price,
            ))
        cursor = ReplayArchive(self.missing).load(FIXTURE_SOURCE, "AAPL", start, start + timedelta(minutes=1), "1m")
        received_seconds, clock_seconds, delays = [], [], []
        for index in range(1, 5):
            snapshot = cursor.advance()
            self.assertEqual(cursor.observation.observation_id, index)
            self.assertEqual(snapshot["candles"][0]["close"], 99 + index)
            received_seconds.append(datetime.fromisoformat(cursor.observation.receipt_time_utc).second)
            clock_seconds.append(cursor.evaluated_at.second)
            delays.append(cursor.next_delay)
        self.assertEqual(received_seconds, [10, 10, 9, 11])
        self.assertEqual(clock_seconds, [10, 10, 10, 11])
        self.assertEqual(delays, [0, 0, 1, None])
