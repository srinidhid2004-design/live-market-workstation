"""Build and independently inspect a disposable constructed replay database."""

import argparse
import hashlib
import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path

from app.observations import UNIX_EPOCH, Observation, ObservationStore


SYMBOL = "AAPL"
SOURCE_NAME = "constructed_test"
START = "2026-11-09T14:30:00Z"
END = "2026-11-09T14:32:00Z"
MINUTE_END = "2026-11-09T14:31:00.000000Z"
ROWS = (
    # Source UTC, receipt UTC, price, cumulative shares, verified source event ID.
    ("14:29:55", "14:29:59", 99, 1000, None),
    ("14:30:05", "14:30:06", 100, 1000, None),
    ("14:31:04", "14:31:05", 110, None, None),
    ("14:30:40", "14:31:07", 109, 1000, "replay-late"),
    ("14:30:40", "14:31:09", 98, 1000, None),
    ("14:30:40", "14:31:11", 105, 1000, "replay-late"),
)


def seed_replay_fixture(path: Path) -> Path:
    """Create one new fixture using the normal recorder's revision logic."""
    path = Path(path).resolve()
    path.touch(exist_ok=False)
    store = ObservationStore(path)
    for source, receipt, price, cumulative_shares, event_id in ROWS:
        source_time = datetime.fromisoformat(f"2026-11-09T{source}Z")
        store.record(Observation(
            source_name=SOURCE_NAME,
            ticker=SYMBOL,
            source_timestamp=(source_time - UNIX_EPOCH) // timedelta(seconds=1),
            source_timestamp_unit="s",
            received_at=datetime.fromisoformat(f"2026-11-09T{receipt}Z"),
            price=price,
            volume_fields={} if cumulative_shares is None else {"day_volume": cumulative_shares},
            verified_event_id=event_id,
        ))
    return path


def fixture_evidence(path: Path) -> dict[str, object]:
    """Independently calculate expected close and volume using stored SQL rows."""
    path = Path(path).resolve()
    with closing(sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)) as db:
        db.execute("PRAGMA query_only = ON")
        schema_version = db.execute("PRAGMA user_version").fetchone()[0]
        ids = [row[0] for row in db.execute("SELECT observation_id FROM observations ORDER BY observation_id")]
        current = db.execute("""
            SELECT observation.observation_id, observation.source_time_utc, observation.price,
                json_extract(observation.volume_fields_json, '$.day_volume')
            FROM observations AS observation
            WHERE observation.source_name = ? AND observation.ticker = ?
                AND observation.source_time_utc < ?
                AND NOT EXISTS (
                    SELECT 1 FROM observations AS revision
                    WHERE revision.revision_of = observation.observation_id
                )
            ORDER BY observation.source_time_utc, observation.observation_id
            """, (SOURCE_NAME, SYMBOL, MINUTE_END)).fetchall()
    minute_start = datetime.fromisoformat(START)
    before = [row for row in current if datetime.fromisoformat(row[1]) < minute_start]
    minute = [row for row in current if datetime.fromisoformat(row[1]) >= minute_start]
    baseline = before[-1][3]
    closing_total = minute[-1][3]
    return {
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "count": len(ids),
        "schema_version": schema_version,
        "ids": ids,
        "current_minute_ids": [row[0] for row in minute],
        "close": minute[-1][2],
        "volume": closing_total - baseline,
        "baseline": baseline,
        "closing_total": closing_total,
    }


def create_replay_test_app():
    from app.main import create_app

    return create_app(
        database_path=Path(os.environ["REPLAY_TEST_DB"]),
        replay_cumulative_fields={SOURCE_NAME: "day_volume"},
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("create", "inspect"))
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    if args.action == "create":
        seed_replay_fixture(args.path)
    print(json.dumps(fixture_evidence(args.path)))


if __name__ == "__main__":
    main()
