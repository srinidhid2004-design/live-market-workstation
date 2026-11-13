import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from app.candles import Candle, form_candles
from app.observations import Observation, ObservationStore, UNIX_EPOCH


SOURCE = "constructed_test"
START = datetime(2026, 11, 9, 15, tzinfo=UTC)
END = START + timedelta(minutes=1)
STAMP = "2026-11-09T15:00:00Z"
EXPECTED = {"timestamp": STAMP, "open": 100, "high": 103, "low": 100, "close": 101, "volume": 11}
FIXTURE = ((-1, 99, 1000), (5, 100, 1004), (20, 103, 1009), (50, 101, 1011))


def make_observation(second: int, price: float, total: int | str | None, **changes) -> Observation:
    source_time = START + timedelta(seconds=second)
    observation = Observation(
        source_name=SOURCE,
        ticker="AAPL",
        source_timestamp=(source_time - UNIX_EPOCH) // timedelta(microseconds=1),
        source_timestamp_unit="us",
        received_at=source_time,
        price=price,
        volume_fields={} if total is None else {"day_volume": total},
    )
    return replace(observation, **changes)


class CandleTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = self.enterContext(TemporaryDirectory(dir=Path(__file__).resolve().parents[1]))
        self.store = ObservationStore(Path(directory) / "constructed-candles.sqlite3")

    def candles(self, evaluated_at=END, *, source_name=SOURCE, ticker="AAPL", field="day_volume"):
        return form_candles(
            self.store, source_name=source_name, ticker=ticker,
            evaluated_at=evaluated_at, cumulative_volume_field=field,
        )

    def target(self, evaluated_at=END, **options) -> Candle:
        return next(candle for candle in self.candles(evaluated_at, **options) if candle.data["timestamp"] == STAMP)

    def test_instructor_fixture_before_and_at_completion(self) -> None:
        for row in FIXTURE:
            self.store.record(make_observation(*row))

        incomplete = self.target(END - timedelta(microseconds=1))
        complete = self.target(END)
        self.assertEqual(incomplete, Candle(EXPECTED, False))
        self.assertEqual(complete, Candle(EXPECTED, True))
        self.assertEqual(self.target(END + timedelta(minutes=1)), complete)

    def test_late_arrival_recalculates_completed_instructor_candle(self) -> None:
        for index in (0, 1, 3):
            self.store.record(make_observation(*FIXTURE[index]))
        before = self.target()
        self.assertEqual(before, Candle({**EXPECTED, "high": 101}, True))

        self.store.record(make_observation(*FIXTURE[2], received_at=END + timedelta(seconds=1)))
        self.assertEqual(self.target(END + timedelta(seconds=1)), Candle(EXPECTED, True))
        self.assertEqual([row.observation_id for row in self.store.read(order="source")], [1, 2, 4, 3])

    def test_exact_repeat_does_not_change_equal_time_close(self) -> None:
        self.store.record(make_observation(*FIXTURE[0]))
        first = make_observation(5, 100, 1004)
        initial = self.store.record(first)
        self.store.record(make_observation(5, 103, 1009))
        repeat = self.store.record(replace(first, received_at=END))

        self.assertFalse(repeat.inserted)
        self.assertEqual(repeat.observation_id, initial.observation_id)
        self.assertEqual(self.target().data, {**EXPECTED, "close": 103, "volume": 9})

    def test_verified_correction_uses_current_revision_and_keeps_history(self) -> None:
        for index, row in enumerate(FIXTURE):
            if index == 2:
                original = make_observation(*row, verified_event_id="constructed-event")
                self.store.record(original)
            else:
                self.store.record(make_observation(*row))
        self.assertEqual(self.target(), Candle(EXPECTED, True))

        correction = self.store.record(replace(original, price=98, received_at=END))
        self.assertEqual(self.target(), Candle({**EXPECTED, "high": 101, "low": 98}, True))
        self.assertEqual([row.price for row in self.store.read(order="source")], [99, 100, 103, 98, 101])
        self.assertEqual([row.price for row in self.store.read(current_only=True, order="source")], [99, 100, 98, 101])
        self.assertEqual(self.store.read()[-1].revision_of, 3)
        self.assertEqual(self.store.read()[-1].observation_id, correction.observation_id)

    def test_correction_that_changes_source_minute_rebuilds_both_minutes(self) -> None:
        original = make_observation(20, 103, 1009, verified_event_id="constructed-event")
        self.store.record(make_observation(*FIXTURE[0]))
        self.store.record(original)
        self.assertEqual(self.target().data["volume"], 9)

        self.store.record(replace(
            original, source_timestamp=original.source_timestamp + 60_000_000, received_at=END,
        ))
        self.assertEqual([candle.data["timestamp"] for candle in self.candles()], [
            "2026-11-09T14:59:00Z", "2026-11-09T15:01:00Z",
        ])
        self.assertEqual(self.candles()[-1].data["volume"], 9)

    def test_ambiguous_equal_times_use_receipt_order_ids(self) -> None:
        self.store.record(make_observation(*FIXTURE[0]))
        self.store.record(make_observation(5, 103, 1004, received_at=END))
        self.store.record(make_observation(5, 100, 1009, received_at=START))

        self.assertEqual(self.target().data, {**EXPECTED, "open": 103, "close": 100, "volume": 9})
        self.assertEqual([row.revision_of for row in self.store.read()], [None, None, None])

    def test_missing_baseline_leaves_unknown_volume(self) -> None:
        for row in FIXTURE[1:]:
            self.store.record(make_observation(*row))
        self.assertEqual(self.target().data, {**EXPECTED, "volume": None})

    def test_baseline_is_latest_valid_value_strictly_before_minute(self) -> None:
        self.store.record(make_observation(-20, 98, 998))
        self.store.record(make_observation(*FIXTURE[0]))
        self.store.record(make_observation(-1, 99, None))
        for row in FIXTURE[1:]:
            self.store.record(make_observation(*row))
        self.assertEqual(self.target().data, EXPECTED)

    def test_volume_reset_within_minute_is_unknown_even_after_recovery(self) -> None:
        for row in (FIXTURE[0], FIXTURE[1], (20, 103, 4), FIXTURE[3]):
            self.store.record(make_observation(*row))
        self.assertEqual(self.target().data, {**EXPECTED, "volume": None})

    def test_volume_reset_from_baseline_is_unknown(self) -> None:
        self.store.record(make_observation(*FIXTURE[0]))
        self.store.record(make_observation(5, 100, 4))
        self.assertIsNone(self.target().data["volume"])

    def test_missing_volume_leaves_unknown_even_with_last_size(self) -> None:
        self.store.record(make_observation(*FIXTURE[0]))
        self.store.record(make_observation(*FIXTURE[1]))
        self.store.record(make_observation(20, 103, None, volume_fields={"last_size": 5}))
        self.store.record(make_observation(*FIXTURE[3]))
        self.assertEqual(self.target().data, {**EXPECTED, "volume": None})

    def test_invalid_cumulative_volume_leaves_unknown(self) -> None:
        self.store.record(make_observation(*FIXTURE[0]))
        self.store.record(make_observation(5, 100, "10.5"))
        self.assertIsNone(self.target().data["volume"])

    def test_known_zero_and_explicit_volume_field(self) -> None:
        self.store.record(make_observation(*FIXTURE[0]))
        self.store.record(make_observation(5, 100, "1000"))
        self.assertEqual(self.target().data["volume"], 0)
        self.assertIsNone(self.target(field=None).data["volume"])

    def test_no_empty_minute_candles(self) -> None:
        self.assertEqual(self.candles(), [])
        self.store.record(make_observation(*FIXTURE[0]))
        self.store.record(make_observation(65, 100, 1004))
        self.assertEqual([candle.data["timestamp"] for candle in self.candles()], [
            "2026-11-09T14:59:00Z", "2026-11-09T15:01:00Z",
        ])

    def test_ticker_and_source_are_isolated_for_prices_and_baseline(self) -> None:
        self.store.record(make_observation(-1, 500, 2, ticker="MSFT"))
        self.store.record(make_observation(-1, 500, 3, source_name="other_constructed_test"))
        self.store.record(make_observation(5, 500, 5, ticker="MSFT"))
        self.store.record(make_observation(5, 500, 6, source_name="other_constructed_test"))
        self.store.record(make_observation(*FIXTURE[1]))

        self.assertEqual(self.target(ticker=" aapl ").data, {
            "timestamp": STAMP, "open": 100, "high": 100, "low": 100, "close": 100, "volume": None,
        })
        self.assertEqual(self.target(ticker="MSFT").data["volume"], 3)

    def test_utc_boundaries_use_half_open_minutes(self) -> None:
        first = make_observation(0, 99, 1000)
        self.store.record(replace(first, source_timestamp=first.source_timestamp - 1))
        self.store.record(make_observation(0, 100, 1004))
        self.store.record(make_observation(60, 103, 1009))
        before, at, after = self.candles()

        self.assertEqual(before.data["timestamp"], "2026-11-09T14:59:00Z")
        self.assertEqual(at.data["volume"], 4)
        self.assertEqual(at.data["close"], 100)
        self.assertTrue(at.is_complete)
        self.assertEqual(after.data["timestamp"], "2026-11-09T15:01:00Z")
        self.assertFalse(after.is_complete)

    def test_evaluation_time_requires_utc(self) -> None:
        for invalid in (END.replace(tzinfo=None), END.astimezone(timezone(timedelta(hours=1)))):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(ValueError, "UTC"):
                self.candles(invalid)
