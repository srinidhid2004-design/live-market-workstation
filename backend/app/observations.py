"""Store normalized market observations and their source evidence in SQLite."""

import argparse
import hashlib
import json
import math
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal


SCHEMA_VERSION = 1
DEFAULT_DATABASE = Path(__file__).resolve().parents[1] / "data" / "observations.sqlite3"
TimestampUnit = Literal["s", "ms", "us"]
MICROSECONDS_PER_UNIT = {"s": 1_000_000, "ms": 1_000, "us": 1}
UNIX_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)

CREATE_OBSERVATIONS = """
CREATE TABLE observations (
    observation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_name TEXT NOT NULL CHECK (length(source_name) > 0),
    ticker TEXT NOT NULL CHECK (length(ticker) > 0),
    source_timestamp INTEGER NOT NULL,
    source_timestamp_unit TEXT NOT NULL CHECK (source_timestamp_unit IN ('s', 'ms', 'us')),
    source_time_utc TEXT NOT NULL,
    receipt_time_utc TEXT NOT NULL,
    price REAL NOT NULL CHECK (price > 0 AND price <= 1.7976931348623157e308),
    volume_fields_json TEXT NOT NULL CHECK (json_valid(volume_fields_json) AND json_type(volume_fields_json) = 'object'),
    source_fields_json TEXT NOT NULL CHECK (json_valid(source_fields_json) AND json_type(source_fields_json) = 'object'),
    fingerprint TEXT NOT NULL UNIQUE CHECK (length(fingerprint) = 64),
    verified_event_id TEXT CHECK (length(verified_event_id) > 0),
    revision_of INTEGER UNIQUE,
    CHECK (revision_of IS NULL OR (verified_event_id IS NOT NULL AND revision_of < observation_id)),
    UNIQUE (observation_id, source_name, ticker, verified_event_id),
    FOREIGN KEY (revision_of, source_name, ticker, verified_event_id)
        REFERENCES observations (observation_id, source_name, ticker, verified_event_id)
) STRICT
"""

READ_BY_RECEIPT = """
SELECT observation.* FROM observations AS observation
WHERE NOT ? OR NOT EXISTS (
    SELECT 1 FROM observations AS revision WHERE revision.revision_of = observation.observation_id
)
ORDER BY observation.observation_id
"""

READ_BY_SOURCE = """
SELECT observation.* FROM observations AS observation
WHERE NOT ? OR NOT EXISTS (
    SELECT 1 FROM observations AS revision WHERE revision.revision_of = observation.observation_id
)
ORDER BY observation.source_time_utc, observation.observation_id
"""


class UnsupportedSchemaVersion(RuntimeError):
    """The database uses an observation schema this recorder cannot open."""


@dataclass(frozen=True)
class Observation:
    source_name: str
    ticker: str
    source_timestamp: int
    source_timestamp_unit: TimestampUnit
    received_at: datetime
    price: float
    volume_fields: dict[str, object] = field(default_factory=dict)
    source_fields: dict[str, object] = field(default_factory=dict)
    verified_event_id: str | None = None


@dataclass(frozen=True)
class RecordResult:
    observation_id: int
    inserted: bool


@dataclass(frozen=True)
class StoredObservation:
    observation_id: int
    source_name: str
    ticker: str
    source_timestamp: int
    source_timestamp_unit: TimestampUnit
    source_time_utc: str
    receipt_time_utc: str
    price: float
    volume_fields: dict[str, object]
    source_fields: dict[str, object]
    fingerprint: str
    verified_event_id: str | None
    revision_of: int | None


def _utc_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _check_json_keys(value: object) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise ValueError("Source JSON keys must be strings.")
            _check_json_keys(child)
    elif isinstance(value, list):
        for child in value:
            _check_json_keys(child)
    elif value is not None and not isinstance(value, (str, int, float, bool)):
        raise ValueError("Source evidence must contain only JSON values.")


def _canonical_json(value: dict[str, object]) -> str:
    _check_json_keys(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _storage_values(observation: Observation) -> dict[str, str | int | float | None]:
    if not isinstance(observation.source_name, str) or not observation.source_name.strip():
        raise ValueError("Source name is required.")
    if not isinstance(observation.ticker, str) or not observation.ticker.strip():
        raise ValueError("Ticker is required.")
    event_id = observation.verified_event_id
    if event_id is not None and (not isinstance(event_id, str) or not event_id.strip()):
        raise ValueError("Verified event ID must be a nonempty string.")
    unit = observation.source_timestamp_unit
    if type(observation.source_timestamp) is not int or unit not in MICROSECONDS_PER_UNIT:
        raise ValueError("Source time must be an integer Unix timestamp with a supported unit.")
    try:
        source_time = UNIX_EPOCH + timedelta(
            microseconds=observation.source_timestamp * MICROSECONDS_PER_UNIT[unit]
        )
    except OverflowError as exc:
        raise ValueError("Source time is outside the supported UTC range.") from exc
    if not isinstance(observation.received_at, datetime) or observation.received_at.utcoffset() is None:
        raise ValueError("Receipt time must be timezone-aware.")
    if type(observation.price) not in (int, float):
        raise ValueError("Price must be numeric.")
    try:
        price = float(observation.price)
    except OverflowError as exc:
        raise ValueError("Price is outside the supported range.") from exc
    if not math.isfinite(price) or price <= 0:
        raise ValueError("Price must be finite and positive.")
    if not isinstance(observation.volume_fields, dict) or not isinstance(observation.source_fields, dict):
        raise ValueError("Volume fields and source evidence must be JSON objects.")

    identity = {
        "source_name": observation.source_name.strip(),
        "ticker": observation.ticker.strip().upper(),
        "source_timestamp": observation.source_timestamp,
        "source_timestamp_unit": unit,
        "price": price,
        "verified_event_id": event_id,
    }
    evidence = {"volume_fields": observation.volume_fields, "source_fields": observation.source_fields}
    fingerprint = hashlib.sha256(_canonical_json({**identity, **evidence}).encode("ascii")).hexdigest()
    return {
        **identity,
        "source_time_utc": _utc_text(source_time),
        "receipt_time_utc": _utc_text(observation.received_at),
        "volume_fields_json": _canonical_json(observation.volume_fields),
        "source_fields_json": _canonical_json(observation.source_fields),
        "fingerprint": fingerprint,
    }


class ObservationStore:
    """Open a file-backed recorder at a caller-supplied or default path."""

    def __init__(self, path: Path = DEFAULT_DATABASE) -> None:
        self.path = Path(path).resolve()
        with self._transaction() as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version == SCHEMA_VERSION:
                return
            if version != 0:
                raise UnsupportedSchemaVersion(f"Unsupported observation schema version: {version}.")
            connection.execute(CREATE_OBSERVATIONS)
            connection.execute("CREATE INDEX observations_source_time ON observations (source_time_utc, observation_id)")
            connection.execute("""
                CREATE INDEX observations_event_versions
                ON observations (source_name, ticker, verified_event_id, observation_id)
                WHERE verified_event_id IS NOT NULL
            """)
            connection.execute("PRAGMA user_version = 1")

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, autocommit=True)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
        except BaseException:
            connection.close()
            raise
        return connection

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
                connection.execute("COMMIT")
            except BaseException:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise

    def record(self, observation: Observation) -> RecordResult:
        """Insert an immutable version or return the existing exact repeat's ID."""
        with self._transaction() as connection:
            values = _storage_values(observation)
            repeat = connection.execute(
                "SELECT observation_id FROM observations WHERE fingerprint = :fingerprint", values
            ).fetchone()
            if repeat is not None:
                return RecordResult(repeat["observation_id"], inserted=False)

            previous = None
            if observation.verified_event_id is not None:
                previous = connection.execute("""
                    SELECT observation_id FROM observations
                    WHERE source_name = :source_name AND ticker = :ticker
                        AND verified_event_id = :verified_event_id
                    ORDER BY observation_id DESC LIMIT 1
                """, values).fetchone()
            values["revision_of"] = previous["observation_id"] if previous is not None else None
            row = connection.execute("""
                INSERT INTO observations (
                    source_name, ticker, source_timestamp, source_timestamp_unit, source_time_utc,
                    receipt_time_utc, price, volume_fields_json, source_fields_json, fingerprint,
                    verified_event_id, revision_of
                ) VALUES (
                    :source_name, :ticker, :source_timestamp, :source_timestamp_unit, :source_time_utc,
                    :receipt_time_utc, :price, :volume_fields_json, :source_fields_json, :fingerprint,
                    :verified_event_id, :revision_of
                ) RETURNING observation_id
            """, values).fetchone()
            return RecordResult(row["observation_id"], inserted=True)

    def read(
        self, *, current_only: bool = False, order: Literal["receipt", "source"] = "receipt"
    ) -> list[StoredObservation]:
        """Read every unique version or just the current versions, in either order."""
        if order not in ("receipt", "source"):
            raise ValueError("Order must be 'receipt' or 'source'.")
        query = READ_BY_RECEIPT if order == "receipt" else READ_BY_SOURCE
        with closing(self._connect()) as connection:
            records = []
            for row in connection.execute(query, (current_only,)):
                fields = dict(row)
                fields["volume_fields"] = json.loads(fields.pop("volume_fields_json"))
                fields["source_fields"] = json.loads(fields.pop("source_fields_json"))
                records.append(StoredObservation(**fields))
            return records


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize the local observation database.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DATABASE, help="Override the database path.")
    ObservationStore(parser.parse_args().db)
    print(f"Observation database ready (schema version {SCHEMA_VERSION}).")


if __name__ == "__main__":
    main()
