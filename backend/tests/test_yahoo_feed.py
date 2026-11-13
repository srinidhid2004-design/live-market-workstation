import asyncio
import base64
import json
import unittest
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

from yfinance.pricing_pb2 import PricingData

from app.yahoo_observations import YahooObservationSource


RECEIVED = datetime(2026, 11, 9, 14, 30, 30, tzinfo=UTC)


def encoded_quote(ticker: str) -> str:
    quote = PricingData(id=ticker, time=1794234600123, price=100.5, day_volume=5000)
    encoded = base64.b64encode(quote.SerializeToString()).decode("ascii")
    return json.dumps({"message": encoded})


class InMemoryConnection:
    def __init__(self, *frames: str) -> None:
        self.frames = frames
        self.send = AsyncMock()
        self.close = AsyncMock()
        self.waiting = asyncio.Event()

    async def __aiter__(self):
        for frame in self.frames:
            yield frame
        self.waiting.set()
        await asyncio.Future()


class YahooObservationSourceTests(unittest.IsolatedAsyncioTestCase):
    async def test_uses_one_aapl_subscription_and_keeps_only_selected_fields(self) -> None:
        connection = InMemoryConnection('{"message":[]}', encoded_quote("MSFT"), encoded_quote("aapl"))
        with patch("app.yahoo_observations._DirectConnection", side_effect=AsyncMock(return_value=connection)) as connect:
            source = YahooObservationSource(clock=lambda: RECEIVED)
            frames = source.observations()
            connect.assert_not_called()
            try:
                observation = await anext(frames)
                self.assertEqual(observation.source_name, "yahoo_finance")
                self.assertEqual(observation.ticker, "AAPL")
                self.assertEqual(observation.price, 100.5)
                self.assertEqual(observation.source_timestamp, 1794234600123)
                self.assertEqual(observation.source_timestamp_unit, "ms")
                self.assertEqual(observation.received_at, RECEIVED)
                self.assertEqual(observation.volume_fields, {"day_volume": "5000"})
                self.assertIsNone(source.cumulative_volume_field)
                self.assertIsNone(observation.verified_event_id)
                connect.assert_called_once()
                self.assertEqual(connect.call_args.kwargs["open_timeout"], 5)
                self.assertEqual(connect.call_args.kwargs["close_timeout"], 2)
                connection.send.assert_awaited_once_with('{"subscribe": ["AAPL"]}')
            finally:
                await frames.aclose()
            connection.close.assert_awaited_once()

    async def test_pending_receive_cancellation_closes_the_provider(self) -> None:
        connection = InMemoryConnection()
        with patch("app.yahoo_observations._DirectConnection", side_effect=AsyncMock(return_value=connection)):
            frames = YahooObservationSource().observations()
            consume = asyncio.create_task(anext(frames))
            try:
                await asyncio.wait_for(connection.waiting.wait(), timeout=1)
            finally:
                consume.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await consume
                await frames.aclose()
            connection.close.assert_awaited_once()

    async def test_handshake_failure_does_not_retry(self) -> None:
        connector = AsyncMock(side_effect=OSError("constructed handshake failure"))
        with patch("app.yahoo_observations._DirectConnection", side_effect=connector):
            frames = YahooObservationSource().observations()
            with self.assertRaises(OSError):
                await anext(frames)
            await frames.aclose()
        connector.assert_awaited_once()
