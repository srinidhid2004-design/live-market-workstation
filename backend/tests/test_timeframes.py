import unittest
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from app.candles import CandleData, form_candles
from app.history import load_candles
from app.observations import Observation, ObservationStore, UNIX_EPOCH
from app.timeframes import aggregate_minutes, session_calendar


SAMPLE = Path(__file__).resolve().parents[1] / "data" / "sample-candles.csv"
OPEN = "2026-11-09T14:30:00Z"
CLOSE = "2026-11-09T21:00:00Z"


def minute(timestamp: str, volume: int | None = 1) -> CandleData:
    return {"timestamp": timestamp, "open": 100, "high": 101, "low": 99, "close": 101, "volume": volume}


class TimeframeTests(unittest.TestCase):
    def test_instructor_sample_is_partial_with_exact_values(self) -> None:
        for interval, count in (("5m", 5), ("1d", 390)):
            with self.subTest(interval=interval):
                result = aggregate_minutes(load_candles(SAMPLE), interval=interval, as_of=datetime.fromisoformat(CLOSE))
                self.assertEqual(result["candles"], [{
                    "timestamp": OPEN, "open": 100, "high": 105, "low": 99, "close": 104, "volume": 3550,
                }])
                self.assertEqual(result["metadata"], [{
                    "timestamp": OPEN, "coverage": "partial", "observed_minutes": 3,
                    "expected_minutes": count, "is_complete": True,
                }])

    def test_gaps_preserve_intraday_buckets_and_daily_sessions(self) -> None:
        second = "2026-11-09T14:35:00Z"
        next_open = "2026-11-10T14:30:00Z"
        rows = [minute(next_open), minute(second), *load_candles(SAMPLE)]
        for interval, timestamps, observed in (("5m", [OPEN, second, next_open], [3, 1, 1]),
                                                ("1d", [OPEN, next_open], [4, 1])):
            result = aggregate_minutes(rows, interval=interval, as_of=datetime.fromisoformat("2026-11-10T21:00:00Z"))
            self.assertEqual([row["timestamp"] for row in result["candles"]], timestamps)
            self.assertEqual([row["observed_minutes"] for row in result["metadata"]], observed)

    def test_hourly_groups_anchor_to_open_and_clip_at_early_close(self) -> None:
        rows = [minute(f"2026-11-27T{stamp}:00Z") for stamp in ("14:29", "14:30", "15:00", "15:30", "17:59", "18:00")]
        result = aggregate_minutes(rows, interval="1h", as_of=datetime.fromisoformat("2026-11-27T18:00:00Z"))
        self.assertEqual([row["timestamp"][11:16] for row in result["candles"]], ["14:30", "15:30", "17:30"])
        self.assertEqual([row["expected_minutes"] for row in result["metadata"]], [60, 60, 30])
        self.assertEqual([row["observed_minutes"] for row in result["metadata"]], [2, 1, 1])
        self.assertTrue(result["metadata"][-1]["is_complete"])
        daily = aggregate_minutes(rows, interval="1d", as_of=datetime.fromisoformat("2026-11-27T17:59:59Z"))
        self.assertEqual(daily["metadata"][0]["expected_minutes"], 210)
        self.assertFalse(daily["metadata"][0]["is_complete"])

    def test_shared_calendar_holiday_and_dst(self) -> None:
        self.assertEqual(session_calendar().name, "XNYS")
        self.assertFalse(session_calendar().is_session("2026-11-26"))
        rows = [minute(stamp) for stamp in (
            "2026-03-06T15:00:00Z", "2026-03-09T14:00:00Z", "2026-11-26T14:30:00Z",
        )]
        result = aggregate_minutes(rows, interval="1d", as_of=datetime.fromisoformat("2026-11-27T21:00:00Z"))
        self.assertEqual([row["timestamp"] for row in result["candles"]], [
            "2026-03-06T14:30:00Z", "2026-03-09T13:30:00Z",
        ])

    def test_unknown_volume_propagates_while_zero_is_known(self) -> None:
        rows = [minute(OPEN, 0), minute("2026-11-09T14:31:00Z", None)]
        for count, expected in ((1, 0), (2, None)):
            result = aggregate_minutes(rows[:count], interval="15m", as_of=datetime.fromisoformat(CLOSE))
            self.assertEqual(result["candles"][0]["volume"], expected)

    def test_as_of_filters_later_minutes_and_tracks_completion_separately(self) -> None:
        result = aggregate_minutes(load_candles(SAMPLE), interval="5m", as_of=datetime.fromisoformat("2026-11-09T14:31:59Z"))
        self.assertEqual(result["candles"][0]["volume"], 2050)
        self.assertEqual(result["metadata"], [{
            "timestamp": OPEN, "coverage": "partial", "observed_minutes": 2,
            "expected_minutes": 5, "is_complete": False,
        }])

    def test_full_coverage_can_precede_completion(self) -> None:
        rows = [minute(f"2026-11-09T14:{minute_number}:00Z") for minute_number in range(30, 35)]
        for as_of, complete in (("2026-11-09T14:34:59Z", False), ("2026-11-09T14:35:00Z", True)):
            result = aggregate_minutes(rows, interval="5m", as_of=datetime.fromisoformat(as_of))
            self.assertEqual(result["metadata"][0]["coverage"], "full")
            self.assertEqual(result["metadata"][0]["is_complete"], complete)

    def test_snapshot_rejects_duplicate_or_non_utc_minute_rows(self) -> None:
        for stamps in ((OPEN, OPEN), ("2026-11-09T14:30:01Z",), ("2026-11-09T09:30:00-05:00",),
                       ("2026-11-09T14:30:00",)):
            with self.subTest(stamps=stamps), self.assertRaises(ValueError):
                aggregate_minutes(map(minute, stamps), interval="5m", as_of=datetime.fromisoformat(CLOSE))

    def test_saved_revision_and_late_receipt_do_not_leak_into_prior_snapshot(self) -> None:
        folder = self.enterContext(TemporaryDirectory(dir=SAMPLE.parents[1]))
        store = ObservationStore(Path(folder) / "constructed-timeframes.sqlite3")
        source = datetime.fromisoformat("2026-11-09T14:30:10Z")
        original = Observation(
            source_name="constructed", ticker="AAPL", source_timestamp=int((source - UNIX_EPOCH).total_seconds()),
            source_timestamp_unit="s", received_at=source, price=100, verified_event_id="test-revision",
        )
        cutoff = datetime.fromisoformat("2026-11-09T14:31:00Z")
        later = datetime.fromisoformat("2026-11-09T14:33:00Z")
        store.record(original)
        store.record(replace(original, price=110, received_at=later))
        store.record(replace(original, source_timestamp=original.source_timestamp + 60,
                             price=105, received_at=later, verified_event_id=None))
        self.assertEqual(len(store.read()), 3)
        for as_of, opening, closing, count in ((cutoff, 100, 100, 1), (later, 110, 105, 2)):
            rows = form_candles(store, source_name="constructed", ticker="AAPL", evaluated_at=as_of, as_of=as_of)
            result = aggregate_minutes((candle.data for candle in rows), interval="5m", as_of=as_of)
            self.assertEqual(result["candles"][0]["open"], opening)
            self.assertEqual(result["candles"][0]["close"], closing)
            self.assertEqual(result["metadata"][0]["observed_minutes"], count)
