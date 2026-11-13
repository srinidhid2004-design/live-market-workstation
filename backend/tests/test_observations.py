import hashlib
import sqlite3
import unittest
from contextlib import closing
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.observations import Observation, ObservationStore, RecordResult, UnsupportedSchemaVersion
from app.yahoo_observations import record_yahoo_message


TEST_OBSERVATION = Observation(
    source_name="constructed_test",
    ticker="AAPL",
    source_timestamp=1_794_234_600_123,
    source_timestamp_unit="ms",
    received_at=datetime(2026, 11, 9, 14, 30, 2, tzinfo=UTC),
    price=100.0,
    volume_fields={"day_volume": "5000", "last_size": 0},
    source_fields={"currency": "USD", "test_revision": 1},
    verified_event_id="constructed-event-1",
)


class ObservationStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = self.enterContext(TemporaryDirectory(dir=Path(__file__).resolve().parents[1]))
        self.path = Path(directory) / "test-observations.sqlite3"

    def test_fresh_schema_version_and_foreign_keys(self) -> None:
        store = ObservationStore(self.path)
        self.assertEqual(store.read(), [])
        for _ in range(2):
            with closing(store._connect()) as connection:
                self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 1)
                self.assertEqual(connection.execute("PRAGMA foreign_keys").fetchone()[0], 1)

    def test_reopening_current_schema_is_idempotent(self) -> None:
        store = ObservationStore(self.path)
        store.record(TEST_OBSERVATION)
        before = hashlib.sha256(self.path.read_bytes()).digest()
        self.assertEqual(ObservationStore(self.path).read(), store.read())
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).digest(), before)

    def test_repeat_uses_canonical_source_content_and_ignores_receipt_time(self) -> None:
        store = ObservationStore(self.path)
        self.assertEqual(store.record(TEST_OBSERVATION), RecordResult(1, True))
        repeat = replace(
            TEST_OBSERVATION,
            received_at=TEST_OBSERVATION.received_at + timedelta(seconds=1),
            volume_fields={"last_size": 0, "day_volume": "5000"},
            source_fields={"test_revision": 1, "currency": "USD"},
        )
        self.assertEqual(store.record(repeat), RecordResult(1, False))
        row, = store.read()
        self.assertEqual(row.receipt_time_utc, "2026-11-09T14:30:02.000000Z")
        self.assertEqual(row.source_timestamp, TEST_OBSERVATION.source_timestamp)
        self.assertEqual(row.source_timestamp_unit, "ms")
        self.assertEqual(row.source_time_utc, "2026-11-09T14:30:00.123000Z")
        self.assertEqual(row.volume_fields, TEST_OBSERVATION.volume_fields)
        self.assertEqual(row.source_fields, TEST_OBSERVATION.source_fields)
        self.assertRegex(row.fingerprint, r"^[a-f0-9]{64}$")

    def test_shared_verified_identity_retains_versions_and_current_revision(self) -> None:
        store = ObservationStore(self.path)
        store.record(TEST_OBSERVATION)
        changed = replace(TEST_OBSERVATION, price=101.0, source_fields={"test_revision": 2})
        store.record(changed)
        changed_again = replace(TEST_OBSERVATION, source_fields={"test_revision": 3})
        store.record(changed_again)
        self.assertEqual(store.record(TEST_OBSERVATION), RecordResult(1, False))
        rows = store.read()
        self.assertEqual([row.price for row in rows], [100.0, 101.0, 100.0])
        self.assertEqual([row.revision_of for row in rows], [None, 1, 2])
        self.assertEqual(len({row.fingerprint for row in rows}), 3)
        self.assertEqual(store.read(current_only=True), [rows[2]])

    def test_changed_messages_with_only_ticker_and_timestamp_are_independent(self) -> None:
        store = ObservationStore(self.path)
        initial = replace(TEST_OBSERVATION, verified_event_id=None)
        store.record(initial)
        store.record(replace(initial, price=101.0))
        rows = store.read()
        self.assertEqual([row.price for row in rows], [100.0, 101.0])
        self.assertTrue(all(row.revision_of is None for row in rows))
        self.assertEqual(store.read(current_only=True), rows)

    def test_verified_identity_is_scoped_to_source_and_ticker(self) -> None:
        store = ObservationStore(self.path)
        for observation in (
            TEST_OBSERVATION,
            replace(TEST_OBSERVATION, ticker="MSFT"),
            replace(TEST_OBSERVATION, source_name="other_constructed_test"),
            replace(TEST_OBSERVATION, price=101.0),
        ):
            store.record(observation)
        self.assertEqual([row.revision_of for row in store.read()], [None, None, None, 1])
        self.assertEqual([row.observation_id for row in store.read(current_only=True)], [2, 3, 4])

    def test_source_and_receipt_order_are_independent_and_ties_are_stable(self) -> None:
        store = ObservationStore(self.path)
        initial = replace(TEST_OBSERVATION, verified_event_id=None)
        late = replace(initial, source_timestamp=initial.source_timestamp - 1000)
        store.record(initial)
        store.record(late)
        store.record(replace(late, price=99.0))
        self.assertEqual([row.observation_id for row in store.read()], [1, 2, 3])
        self.assertEqual([row.observation_id for row in store.read(order="source")], [2, 3, 1])

    def test_persistence_after_close_and_reopen(self) -> None:
        store = ObservationStore(self.path)
        store.record(TEST_OBSERVATION)
        store.record(replace(TEST_OBSERVATION, price=101.0))
        history = store.read()
        del store
        reopened = ObservationStore(self.path)
        self.assertEqual(reopened.read(), history)
        self.assertEqual(reopened.read(current_only=True), [history[1]])

    def test_unsupported_version_refused_without_changing_file(self) -> None:
        with closing(sqlite3.connect(self.path, autocommit=True)) as connection:
            connection.execute("PRAGMA user_version = 99")
        before = self.path.read_bytes()
        with self.assertRaisesRegex(UnsupportedSchemaVersion, "99"):
            ObservationStore(self.path)
        self.assertEqual(self.path.read_bytes(), before)

    def test_invalid_observation_rolls_back_and_leaves_next_write_usable(self) -> None:
        store = ObservationStore(self.path)
        store.record(TEST_OBSERVATION)
        statements = []

        def traced_connection() -> sqlite3.Connection:
            connection = original_connect()
            connection.set_trace_callback(statements.append)
            return connection

        original_connect = store._connect
        with patch.object(store, "_connect", side_effect=traced_connection):
            with self.assertRaisesRegex(ValueError, "finite and positive"):
                store.record(replace(TEST_OBSERVATION, price=float("nan")))
        self.assertEqual(statements, ["BEGIN IMMEDIATE", "ROLLBACK"])
        self.assertEqual(len(store.read()), 1)
        self.assertEqual(store.record(replace(TEST_OBSERVATION, price=101.0)), RecordResult(2, True))

    def test_integer_units_and_receipt_offset_normalize_to_utc(self) -> None:
        store = ObservationStore(self.path)
        for time, unit in ((1, "s"), (1000, "ms"), (1_000_000, "us")):
            store.record(replace(
                TEST_OBSERVATION, verified_event_id=None, source_timestamp=time,
                source_timestamp_unit=unit, received_at=datetime(1970, 1, 1, 1, 0, 2, tzinfo=timezone(timedelta(hours=1))),
            ))
        rows = store.read()
        self.assertEqual([row.source_timestamp_unit for row in rows], ["s", "ms", "us"])
        self.assertTrue(all(row.source_time_utc == "1970-01-01T00:00:01.000000Z" for row in rows))
        self.assertTrue(all(row.receipt_time_utc == "1970-01-01T00:00:02.000000Z" for row in rows))

    def test_constructed_yahoo_payload_preserves_selected_evidence_without_linking(self) -> None:
        store = ObservationStore(self.path)
        constructed = {
            "id": "aapl", "time": "1794234600123", "price": 100.0, "currency": "USD",
            "day_volume": "5000", "last_size": 0, "bid": 99.0,
            "transport_metadata": "discard this constructed field",
        }
        receipt = TEST_OBSERVATION.received_at
        self.assertEqual(record_yahoo_message(store, constructed, received_at=receipt), RecordResult(1, True))
        self.assertEqual(record_yahoo_message(store, constructed, received_at=receipt), RecordResult(1, False))
        record_yahoo_message(store, {**constructed, "bid": 100.0}, received_at=receipt)
        first, second = store.read(current_only=True)
        self.assertEqual((first.source_name, first.ticker, first.source_timestamp), ("yahoo_finance", "AAPL", 1794234600123))
        self.assertEqual(first.volume_fields, {"day_volume": "5000", "last_size": 0})
        self.assertEqual(first.source_fields, {
            "id": "aapl", "time": "1794234600123", "price": 100.0, "currency": "USD", "bid": 99.0,
        })
        self.assertEqual(second.source_fields["bid"], 100.0)
        self.assertIsNone(second.verified_event_id)
        self.assertIsNone(second.revision_of)
