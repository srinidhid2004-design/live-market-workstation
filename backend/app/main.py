import re
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from fastapi import FastAPI, HTTPException, Request

from .candles import MINUTE
from .history import load_candles
from .timeframes import INTERVAL_MINUTES, SYMBOL, HistoryResponse, Interval, aggregate_minutes, session_calendar

app = FastAPI(title="Live Market Workstation")
HISTORY_FILE = Path(__file__).resolve().parents[1] / "data" / "sample-candles.csv"
UTC_TIME = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?(?:Z|\+00:00)")


def _evaluation_time(as_of: str | None) -> datetime:
    now = datetime.now(UTC)
    if as_of is None:
        return now
    error = HTTPException(status_code=422, detail="as_of must be a supported UTC timestamp at or before now.")
    if not UTC_TIME.fullmatch(as_of):
        raise error
    try:
        value = datetime.fromisoformat(as_of)
    except ValueError:
        raise error from None
    calendar = session_calendar()
    if value > now or not calendar.first_session.date() <= value.date() <= calendar.last_session.date():
        raise error
    return value


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "healthy"}


@app.get("/api/history")
def history(
    request: Request, symbol: str = SYMBOL, interval: str = "1m", as_of: str | None = None,
) -> HistoryResponse:
    seen = set()
    for key, _ in request.query_params.multi_items():
        if key not in {"symbol", "interval", "as_of"} or key in seen:
            raise HTTPException(status_code=422, detail="Invalid history query parameters.")
        seen.add(key)
    if symbol != SYMBOL:
        raise HTTPException(status_code=422, detail="Unsupported symbol.")
    if interval not in INTERVAL_MINUTES:
        raise HTTPException(status_code=422, detail="Unsupported interval.")
    evaluated_at = _evaluation_time(as_of)
    try:
        minutes = load_candles(HISTORY_FILE)
        available = (row for row in minutes if evaluated_at - datetime.fromisoformat(row["timestamp"]) >= MINUTE)
        return aggregate_minutes(available, interval=cast(Interval, interval), as_of=evaluated_at)
    except ValueError:
        raise HTTPException(status_code=500, detail="Historical candle data is unavailable.") from None
