"""Read and reconstruct a bounded SQLite recording in original arrival order."""

import re
import sqlite3
from collections.abc import Iterator, Mapping
from contextlib import closing, contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from time import monotonic
from typing import TypedDict

from .candles import form_current_candles
from .observations import SCHEMA_VERSION, StoredObservation, decode_stored_observation
from .timeframes import INTERVAL_MINUTES, HistoryResponse, Interval, aggregate_minutes, utc_text


MAX_RANGE = timedelta(hours=24)
MAX_EVENTS = 1000
MAX_CONTEXT = 4000
MAX_COVERAGE = 64
SYMBOL_PATTERN = re.compile(r"[A-Z][A-Z0-9.\-]{0,15}")


class ReplaySelectionError(ValueError):
    """The requested selection is invalid or exceeds the replay budget."""


class ReplayUnavailable(RuntimeError):
    """The recording cannot be read safely."""


class ReplayCoverage(TypedDict):
    source: str
    symbol: str
    start: str
    end: str
    count: int


def _valid_pair(source: str, symbol: str) -> bool:
    return (
        0 < len(source) <= 64 and source == source.strip() and source.isprintable()
        and SYMBOL_PATTERN.fullmatch(symbol) is not None
    )


def _storage_time(value: datetime) -> str:
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _source_minute(observation: StoredObservation) -> str:
    return observation.source_time_utc[:16] + ":00Z"


class ReplayCursor:
    """Reconstruct one immutable selection without writing any observations."""

    def __init__(
        self, *, symbol: str, interval: Interval, start: datetime, end: datetime,
        seed: list[StoredObservation], rows: list[StoredObservation], event_ids: list[int],
        cumulative_field: str | None,
    ) -> None:
        self.symbol = symbol
        self.interval = interval
        self._start = start
        self._end = end
        self._seed = seed
        self._rows = rows
        self._event_ids = event_ids
        self._events = {row.observation_id: row for row in rows}
        self._cumulative_field = cumulative_field
        self.volume_unit = "shares" if cumulative_field is not None else None
        self.count = len(event_ids)
        self.reset()

    def reset(self) -> HistoryResponse:
        self.position = 0
        self.observation: StoredObservation | None = None
        self.evaluated_at = self._start
        self._current = {row.observation_id: row for row in self._seed}
        self._next_row = 0
        self._touched_minutes: set[str] = set()
        return self.frame()

    @property
    def next_delay(self) -> float | None:
        if self.position == self.count:
            return None
        if not self.position:
            return 0.0
        upcoming = self._events[self._event_ids[self.position]]
        return max(0.0, (datetime.fromisoformat(upcoming.receipt_time_utc) - self.evaluated_at).total_seconds())

    def advance(self) -> HistoryResponse:
        if self.position == self.count:
            raise ReplaySelectionError("Replay has reached the end of its selection.")
        event_id = self._event_ids[self.position]
        for index in range(self._next_row, len(self._rows)):
            row = self._rows[index]
            previous = self._current.pop(row.revision_of, None) if row.revision_of is not None else None
            self._current[row.observation_id] = row
            if row.observation_id == event_id:
                self._next_row = index + 1
                self.observation = row
                self._touched_minutes.add(_source_minute(row))
                if previous is not None:
                    self._touched_minutes.add(_source_minute(previous))
                break
        assert self.observation is not None
        self.evaluated_at = max(self.evaluated_at, datetime.fromisoformat(self.observation.receipt_time_utc))
        self.position += 1
        return self.frame()

    def complete(self) -> HistoryResponse:
        if self.position != self.count:
            raise ReplaySelectionError("Replay still has observations to play.")
        self.evaluated_at = self._end
        return self.frame()

    def frame(self) -> HistoryResponse:
        if not self.position:
            return {
                "symbol": self.symbol, "interval": self.interval, "as_of": utc_text(self.evaluated_at),
                "candles": [], "metadata": [],
            }
        cutoff = _storage_time(self.evaluated_at)
        visible = sorted(
            (row for row in self._current.values() if row.source_time_utc <= cutoff),
            key=lambda row: (row.source_time_utc, row.observation_id),
        )
        candles = form_current_candles(
            visible, evaluated_at=self.evaluated_at, cumulative_volume_field=self._cumulative_field,
        )
        return aggregate_minutes(
            (candle.data for candle in candles), interval=self.interval, as_of=self.evaluated_at,
            symbol=self.symbol, touched_minutes=self._touched_minutes,
        )


class ReplayArchive:
    """Open an existing recorder database with read-only SQLite settings."""

    def __init__(self, path: Path, *, cumulative_fields: Mapping[str, str] | None = None) -> None:
        self.path = Path(path).resolve()
        self._cumulative_fields = dict(cumulative_fields or {})

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        # SQLite may create WAL sidecars even when the main database is opened read-only.
        with self.path.open("rb") as stream:
            header = stream.read(20)
        if not header.startswith(b"SQLite format 3\x00") or header[18:20] != b"\x01\x01":
            raise ReplayUnavailable("Replay requires an existing rollback-journal recorder database.")

        with closing(sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=1, autocommit=True)) as db:
            db.row_factory = sqlite3.Row
            db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 16 * 1024)
            deadline = monotonic() + 2
            db.set_progress_handler(lambda: int(monotonic() >= deadline), 1000)
            db.execute("PRAGMA query_only = ON")
            db.execute("PRAGMA temp_store = MEMORY")
            db.execute("BEGIN")
            if db.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
                raise ReplayUnavailable("The recording uses an unsupported schema.")
            yield db

    def coverage(self) -> list[ReplayCoverage]:
        try:
            with self.connect() as db:
                rows = db.execute("""
                    SELECT source_name, ticker, min(receipt_time_utc) AS first,
                        max(receipt_time_utc) AS last, count(*) AS count
                    FROM observations
                    WHERE length(source_name) BETWEEN 1 AND 64 AND length(ticker) BETWEEN 1 AND 16
                    GROUP BY source_name, ticker ORDER BY ticker, source_name LIMIT ?
                """, (MAX_COVERAGE + 1,)).fetchall()
                if len(rows) > MAX_COVERAGE:
                    raise ReplayUnavailable("The recording contains too many source and symbol pairs.")
                return [
                    {"source": row["source_name"], "symbol": row["ticker"], "start": row["first"],
                     "end": _storage_time(datetime.fromisoformat(row["last"]) + timedelta(microseconds=1)),
                     "count": row["count"]}
                    for row in rows if _valid_pair(row["source_name"], row["ticker"])
                ]
        except FileNotFoundError:
            return []
        except (sqlite3.Error, OSError, ValueError, OverflowError) as exc:
            raise ReplayUnavailable("Could not read the recording.") from exc

    def load(self, source: str, symbol: str, start: datetime, end: datetime, interval: Interval) -> ReplayCursor:
        if not _valid_pair(source, symbol) or interval not in INTERVAL_MINUTES:
            raise ReplaySelectionError("Choose a valid source, symbol, and interval.")
        if start.utcoffset() != timedelta(0) or end.utcoffset() != timedelta(0) or not timedelta(0) < end - start <= MAX_RANGE:
            raise ReplaySelectionError("Choose a UTC range longer than zero and no longer than 24 hours.")
        try:
            with self.connect() as db:
                seed, rows, event_ids = self._load_rows(db, source, symbol, start, end)
        except FileNotFoundError:
            seed, rows, event_ids = [], [], []
        except ReplaySelectionError:
            raise
        except (sqlite3.Error, OSError, ValueError) as exc:
            raise ReplayUnavailable("Could not read the recording.") from exc
        return ReplayCursor(
            symbol=symbol, interval=interval, start=start, end=end, seed=seed, rows=rows,
            event_ids=event_ids, cumulative_field=self._cumulative_fields.get(source),
        )

    @staticmethod
    def _load_rows(
        db: sqlite3.Connection, source: str, symbol: str, start: datetime, end: datetime,
    ) -> tuple[list[StoredObservation], list[StoredObservation], list[int]]:
        event_ids = [row[0] for row in db.execute("""
            SELECT observation_id FROM observations WHERE source_name = ? AND ticker = ?
                AND receipt_time_utc >= ? AND receipt_time_utc < ?
            ORDER BY observation_id LIMIT ?
        """, (source, symbol, _storage_time(start), _storage_time(end), MAX_EVENTS + 1))]
        if len(event_ids) > MAX_EVENTS:
            raise ReplaySelectionError("This selection has too many observations. Choose a shorter range.")
        if not event_ids:
            return [], [], []

        first, last = event_ids[0], event_ids[-1]
        seed = db.execute("""
            SELECT observation.* FROM observations AS observation
            WHERE observation.source_name = ? AND observation.ticker = ?
                AND observation.observation_id < ? AND NOT EXISTS (
                    SELECT 1 FROM observations AS revision WHERE revision.revision_of = observation.observation_id
                        AND revision.observation_id < ?
                )
            ORDER BY observation.observation_id LIMIT ?
        """, (source, symbol, first, first, MAX_CONTEXT + 1)).fetchall()
        if len(seed) > MAX_CONTEXT:
            raise ReplaySelectionError("This selection needs more historical context than replay supports.")

        rows = db.execute("""
            SELECT * FROM observations WHERE source_name = ? AND ticker = ? AND observation_id BETWEEN ? AND ?
            ORDER BY observation_id LIMIT ?
        """, (source, symbol, first, last, len(event_ids) + MAX_CONTEXT - len(seed) + 1)).fetchall()
        if len(seed) + len(rows) - len(event_ids) > MAX_CONTEXT:
            raise ReplaySelectionError("This selection needs more historical context than replay supports.")
        return ([decode_stored_observation(row) for row in seed],
                [decode_stored_observation(row) for row in rows], event_ids)
