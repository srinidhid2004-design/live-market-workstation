"""Adapt a decoded yfinance WebSocket message to the observation recorder."""

import re
from collections.abc import Mapping
from datetime import datetime

from .observations import Observation, ObservationStore, RecordResult


VOLUME_FIELDS = ("day_volume", "last_size", "vol_24hr", "vol_all_currencies")
# The PricingData fields decoded by yfinance 1.8.0, excluding the volume fields above.
SOURCE_FIELDS = (
    "id", "time", "price", "currency", "exchange", "quote_type", "market_hours",
    "change_percent", "day_high", "day_low", "change", "short_name", "expire_date",
    "open_price", "previous_close", "strike_price", "underlying_symbol", "open_interest",
    "options_type", "mini_option", "bid", "bid_size", "ask", "ask_size", "price_hint",
    "from_currency", "last_market", "circulating_supply", "market_cap",
)


def record_yahoo_message(
    store: ObservationStore, message: Mapping[str, object], *, received_at: datetime
) -> RecordResult:
    """Record the decoded update with the receipt time captured by the receiver."""
    ticker = message.get("id")
    timestamp = message.get("time")
    price = message.get("price")
    if not isinstance(ticker, str):
        raise ValueError("Yahoo message requires a ticker.")
    if isinstance(timestamp, str) and re.fullmatch(r"-?[0-9]+", timestamp):
        timestamp = int(timestamp)
    if type(timestamp) is not int:
        raise ValueError("Yahoo message requires an integer Unix millisecond timestamp.")
    if type(price) not in (int, float):
        raise ValueError("Yahoo message requires a numeric price.")

    volume = {key: message[key] for key in VOLUME_FIELDS if key in message}
    evidence = {key: message[key] for key in SOURCE_FIELDS if key in message}
    if any(type(value) not in (int, float, str) for value in (*volume.values(), *evidence.values())):
        raise ValueError("Yahoo market fields must contain scalar values.")
    return store.record(Observation(
        source_name="yahoo_finance",
        ticker=ticker,
        source_timestamp=timestamp,
        source_timestamp_unit="ms",
        received_at=received_at,
        price=price,
        volume_fields=volume,
        source_fields=evidence,
    ))
