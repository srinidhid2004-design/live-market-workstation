from pathlib import Path

from fastapi import FastAPI, HTTPException

from .history import Candle, HistoryDataError, load_candles

app = FastAPI(title="Live Market Workstation")
HISTORY_FILE = Path(__file__).resolve().parents[1] / "data" / "sample-candles.csv"


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "healthy"}


@app.get("/api/history")
def history() -> list[Candle]:
    try:
        return load_candles(HISTORY_FILE)
    except HistoryDataError:
        raise HTTPException(status_code=500, detail="Historical candle data is unavailable.") from None
