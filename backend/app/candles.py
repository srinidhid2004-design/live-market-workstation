"""Form one-minute UTC candles from the current saved observation versions."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from itertools import groupby, pairwise
from typing import TypedDict

from .observations import ObservationStore, StoredObservation


MINUTE = timedelta(minutes=1)


class CandleData(TypedDict):
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: int | None


@dataclass(frozen=True)
class Candle:
    data: CandleData
    is_complete: bool


def _minute_start(observation: StoredObservation) -> datetime:
    return datetime.fromisoformat(observation.source_time_utc).replace(second=0, microsecond=0)


def _cumulative_total(value: object) -> int | None:
    if type(value) is int and value >= 0:
        return value
    if isinstance(value, str) and value.isascii() and value.isdecimal():
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _visible_versions(
    store: ObservationStore, source_name: str, ticker: str, as_of: datetime,
) -> list[StoredObservation]:
    cutoff = as_of.isoformat(timespec="microseconds").replace("+00:00", "Z")
    roots: dict[int, int] = {}
    visible: dict[int, StoredObservation] = {}
    for row in store.read():
        if row.source_name != source_name or row.ticker != ticker:
            continue
        root = row.observation_id if row.revision_of is None else roots[row.revision_of]
        roots[row.observation_id] = root
        if row.receipt_time_utc <= cutoff:
            visible[root] = row
    return sorted(
        (row for row in visible.values() if row.source_time_utc <= cutoff),
        key=lambda row: (row.source_time_utc, row.observation_id),
    )


def form_candles(
    store: ObservationStore,
    *,
    source_name: str,
    ticker: str,
    evaluated_at: datetime,
    cumulative_volume_field: str | None = None,
    as_of: datetime | None = None,
) -> list[Candle]:
    """Rebuild one source/ticker's candles from a single current-version read.

    Supply a volume field only when its cumulative session semantics are known.
    The evaluation time determines completion; the read determines candle values.
    Supply as_of to select the revisions available at that UTC receipt cutoff.
    """
    if evaluated_at.utcoffset() != timedelta(0):
        raise ValueError("Candle evaluation time must be timezone-aware UTC.")
    evaluated_at = evaluated_at.astimezone(UTC)
    source_name = source_name.strip()
    ticker = ticker.strip().upper()
    if not source_name or not ticker:
        raise ValueError("A source name and ticker are required.")

    if as_of is None:
        observations = (
            row for row in store.read(current_only=True, order="source")
            if row.source_name == source_name and row.ticker == ticker
        )
    else:
        if as_of.utcoffset() != timedelta(0) or as_of > evaluated_at:
            raise ValueError("The UTC receipt cutoff must be at or before evaluation time.")
        observations = _visible_versions(store, source_name, ticker, as_of.astimezone(UTC))
    return form_current_candles(
        observations, evaluated_at=evaluated_at, cumulative_volume_field=cumulative_volume_field,
    )


def form_current_candles(
    observations: Iterable[StoredObservation], *, evaluated_at: datetime,
    cumulative_volume_field: str | None = None,
) -> list[Candle]:
    """Build UTC minutes from one source and symbol's source-ordered current rows."""
    baseline: int | None = None
    candles: list[Candle] = []
    for minute, rows in groupby(observations, key=_minute_start):
        prices = []
        totals = []
        for row in rows:
            prices.append(row.price)
            if cumulative_volume_field is not None:
                total = _cumulative_total(row.volume_fields.get(cumulative_volume_field))
                if total is not None:
                    totals.append(total)

        volume = None
        if baseline is not None and len(totals) == len(prices):
            if all(left <= right for left, right in pairwise([baseline, *totals])):
                volume = totals[-1] - baseline
        if totals:
            baseline = totals[-1]

        candles.append(Candle(
            data={
                "timestamp": minute.isoformat(timespec="seconds").replace("+00:00", "Z"),
                "open": prices[0],
                "high": max(prices),
                "low": min(prices),
                "close": prices[-1],
                "volume": volume,
            },
            is_complete=evaluated_at - minute >= MINUTE,
        ))
    return candles
