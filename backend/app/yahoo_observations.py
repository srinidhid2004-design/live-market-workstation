"""Normalize Yahoo messages and expose an opt-in AAPL observation source."""

import json
import logging
import re
from collections.abc import AsyncGenerator, Callable, Mapping
from contextlib import aclosing
from datetime import UTC, datetime
from typing import Literal

from google.protobuf.message import DecodeError
from websockets.asyncio.client import connect
from yfinance import AsyncWebSocket

from .observations import Observation, ObservationStore, RecordResult
from .timeframes import SYMBOL


SOURCE_NAME = "yahoo_finance"
VOLUME_FIELDS = ("day_volume", "last_size", "vol_24hr", "vol_all_currencies")
# The PricingData fields decoded by yfinance 1.8.0, excluding the volume fields above.
SOURCE_FIELDS = (
    "id", "time", "price", "currency", "exchange", "quote_type", "market_hours",
    "change_percent", "day_high", "day_low", "change", "short_name", "expire_date",
    "open_price", "previous_close", "strike_price", "underlying_symbol", "open_interest",
    "options_type", "mini_option", "bid", "bid_size", "ask", "ask_size", "price_hint",
    "from_currency", "last_market", "circulating_supply", "market_cap",
)


def normalize_yahoo_message(message: Mapping[str, object], *, received_at: datetime) -> Observation:
    """Select market fields and preserve the receipt time captured by the receiver."""
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
    return Observation(
        source_name=SOURCE_NAME,
        ticker=ticker.strip().upper(),
        source_timestamp=timestamp,
        source_timestamp_unit="ms",
        received_at=received_at,
        price=price,
        volume_fields=volume,
        source_fields=evidence,
    )


def record_yahoo_message(
    store: ObservationStore, message: Mapping[str, object], *, received_at: datetime
) -> RecordResult:
    """Record an already-decoded update."""
    return store.record(normalize_yahoo_message(message, received_at=received_at))


class _DirectConnection(connect):
    def process_redirect(self, exc: Exception) -> Exception:
        return exc


class _OneSubscription(AsyncWebSocket):
    """Use the pinned yfinance decoder with one subscription and no reconnect."""

    def __init__(self) -> None:
        super().__init__(verbose=False)
        self.logger = logging.Logger("yahoo_feed")
        self.logger.addHandler(logging.NullHandler())
        self.logger.propagate = False

    async def _connect(self) -> None:
        if self._ws is None:
            self._ws = await _DirectConnection(
                self.url, proxy=None, open_timeout=5, close_timeout=2,
                max_size=65_536, max_queue=4, logger=self.logger,
            )

    async def _periodic_subscribe(self) -> None:
        # yfinance 1.8.0 starts this task from subscribe(). Send only the initial subscription.
        return

    async def decoded_frames(
        self, clock: Callable[[], datetime],
    ) -> AsyncGenerator[tuple[Mapping[str, object], datetime], None]:
        async for frame in self._ws:
            received_at = clock()
            try:
                payload = json.loads(frame)
                encoded = payload.get("message") if isinstance(payload, dict) else None
                if not isinstance(encoded, str) or not encoded:
                    continue
                message = self._decode_message(encoded)
            except (ValueError, DecodeError):
                continue
            yield message, received_at


def _utc_now() -> datetime:
    return datetime.now(UTC)


class YahooObservationSource:
    """A lifecycle-owned source. Construction does not open any network connection."""

    source_name = SOURCE_NAME
    data_mode: Literal["live"] = "live"
    cumulative_volume_field = None

    def __init__(self, clock: Callable[[], datetime] = _utc_now) -> None:
        self._clock = clock

    async def observations(self) -> AsyncGenerator[Observation, None]:
        client = _OneSubscription()
        try:
            await client.subscribe(SYMBOL)
            async with aclosing(client.decoded_frames(self._clock)) as frames:
                async for message, received_at in frames:
                    try:
                        observation = normalize_yahoo_message(message, received_at=received_at)
                    except ValueError:
                        continue
                    if observation.ticker == SYMBOL:
                        yield observation
        finally:
            await client.close()
