"""Aggregate one-minute AAPL snapshots within the regular exchange session."""

from collections.abc import Iterable
from datetime import date, datetime, timedelta
from functools import lru_cache
from typing import Literal, TypedDict

import exchange_calendars
from exchange_calendars import ExchangeCalendar

from .candles import MINUTE, CandleData


SYMBOL = "AAPL"
Interval = Literal["1m", "5m", "15m", "1h", "1d"]
INTERVAL_MINUTES: dict[Interval, int] = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "1d": 0}


class CandleMetadata(TypedDict):
    timestamp: str
    coverage: Literal["full", "partial"]
    observed_minutes: int
    expected_minutes: int
    is_complete: bool


class HistoryResponse(TypedDict):
    symbol: Literal["AAPL"]
    interval: Interval
    as_of: str
    candles: list[CandleData]
    metadata: list[CandleMetadata]


@lru_cache(maxsize=1)
def session_calendar() -> ExchangeCalendar:
    # XNAS is an alias for the library's shared XNYS schedule.
    return exchange_calendars.get_calendar("XNAS")


def utc_text(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _source_minute(candle: CandleData) -> datetime:
    stamp = datetime.fromisoformat(candle["timestamp"])
    if stamp.utcoffset() != timedelta(0) or stamp.second or stamp.microsecond:
        raise ValueError("Source candles must be aligned to UTC minutes.")
    return stamp


def aggregate_minutes(
    minutes: Iterable[CandleData], *, interval: Interval, as_of: datetime,
) -> HistoryResponse:
    """Group an as-of snapshot containing at most one candle per source minute."""
    if as_of.utcoffset() != timedelta(0):
        raise ValueError("Evaluation time must be timezone-aware UTC.")
    width = INTERVAL_MINUTES[interval] * MINUTE
    calendar = session_calendar()
    first_date, last_date = calendar.first_session.date(), calendar.last_session.date()
    sessions: dict[date, tuple[datetime, datetime] | None] = {}
    seen: set[datetime] = set()
    groups: dict[tuple[datetime, datetime], list[CandleData]] = {}
    for stamp, candle in sorted(
        ((_source_minute(candle), candle) for candle in minutes),
        key=lambda entry: entry[0],
    ):
        if stamp > as_of:
            break
        if stamp in seen:
            raise ValueError("Each source minute must have a single current candle.")
        seen.add(stamp)
        session_date = stamp.date()
        if not first_date <= session_date <= last_date:
            continue
        if session_date not in sessions:
            label = session_date.isoformat()
            if calendar.is_session(label):
                opening, closing = calendar.session_open_close(label)
                sessions[session_date] = (opening.to_pydatetime(), closing.to_pydatetime())
            else:
                sessions[session_date] = None
        session = sessions[session_date]
        if session is None:
            continue
        opening, closing = session
        if not opening <= stamp < closing:
            continue
        start, end = opening, closing
        if width:
            start = opening + ((stamp - opening) // width) * width
            end = min(start + width, closing)
        groups.setdefault((start, end), []).append(candle)

    candles: list[CandleData] = []
    metadata: list[CandleMetadata] = []
    for (start, end), rows in groups.items():
        timestamp = utc_text(start)
        volumes = [row["volume"] for row in rows if row["volume"] is not None]
        expected = (end - start) // MINUTE
        candles.append({
            "timestamp": timestamp,
            "open": rows[0]["open"],
            "high": max(row["high"] for row in rows),
            "low": min(row["low"] for row in rows),
            "close": rows[-1]["close"],
            "volume": sum(volumes) if len(volumes) == len(rows) else None,
        })
        metadata.append({
            "timestamp": timestamp,
            "coverage": "full" if len(rows) == expected else "partial",
            "observed_minutes": len(rows),
            "expected_minutes": expected,
            "is_complete": as_of >= end,
        })
    return {"symbol": SYMBOL, "interval": interval, "as_of": utc_text(as_of), "candles": candles, "metadata": metadata}
