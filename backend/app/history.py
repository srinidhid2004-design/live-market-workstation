import csv
import math
import re
from datetime import datetime
from pathlib import Path
from typing import TypedDict


FIELDS = ("timestamp", "open", "high", "low", "close", "volume")
UTC_MINUTE = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:00(?:\.0+)?(?:Z|\+00:00)"
)
VOLUME = re.compile(r"[0-9]+")


class Candle(TypedDict):
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: int


class HistoryDataError(ValueError):
    """The candle file cannot be read or does not match the history contract."""


def load_candles(path: Path) -> list[Candle]:
    candles: list[Candle] = []
    timestamps: set[str] = set()
    try:
        with path.open(encoding="utf-8", newline="") as source:
            reader = csv.reader(source, strict=True)
            if next(reader, None) != list(FIELDS):
                raise ValueError("Invalid candle header")

            for timestamp, open_text, high_text, low_text, close_text, volume_text in reader:
                if not UTC_MINUTE.fullmatch(timestamp):
                    raise ValueError("Invalid UTC minute timestamp")
                minute = datetime.fromisoformat(timestamp)
                timestamp = minute.isoformat(timespec="seconds").replace("+00:00", "Z")
                if timestamp in timestamps:
                    raise ValueError("Duplicate candle timestamp")

                opening, high, low, close = map(
                    float, (open_text, high_text, low_text, close_text)
                )
                if not all(map(math.isfinite, (opening, high, low, close))):
                    raise ValueError("Nonfinite candle price")
                if not (low <= opening <= high and low <= close <= high):
                    raise ValueError("Invalid OHLC bounds")
                if not VOLUME.fullmatch(volume_text):
                    raise ValueError("Invalid candle volume")

                candles.append(
                    Candle(
                        timestamp=timestamp,
                        open=opening,
                        high=high,
                        low=low,
                        close=close,
                        volume=int(volume_text),
                    )
                )
                timestamps.add(timestamp)
    except (OSError, ValueError, csv.Error) as error:
        raise HistoryDataError("Candle history could not be loaded") from error

    return sorted(candles, key=lambda candle: candle["timestamp"])
