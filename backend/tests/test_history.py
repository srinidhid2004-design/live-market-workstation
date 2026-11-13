import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import httpx

from app.history import Candle, HistoryDataError, load_candles
from app.main import HISTORY_FILE, app


HEADER = "timestamp,open,high,low,close,volume"
FIRST_ROW = "2026-11-09T14:30:00Z,100,103,99,102,1200"
SECOND_ROW = "2026-11-09T14:31:00Z,102,104,100,101,850"
EXPECTED_TIMES = [
    "2026-11-09T14:30:00Z",
    "2026-11-09T14:31:00Z",
    "2026-11-09T14:32:00Z",
]
SECOND_CANDLE = {
    "timestamp": "2026-11-09T14:31:00Z",
    "open": 102,
    "high": 104,
    "low": 100,
    "close": 101,
    "volume": 850,
}


class HistoryLoaderTest(unittest.TestCase):
    def load_fixture(self, *lines: str) -> list[Candle]:
        with TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as directory:
            path = Path(directory) / "candles.csv"
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return load_candles(path)

    def test_sample_has_three_ordered_candles_and_exact_second_candle(self) -> None:
        candles = load_candles(HISTORY_FILE)
        self.assertEqual([candle["timestamp"] for candle in candles], EXPECTED_TIMES)
        self.assertEqual(candles[1], SECOND_CANDLE)

    def test_out_of_order_rows_are_sorted_and_timestamps_normalized(self) -> None:
        offset_row = FIRST_ROW.replace(":00Z", ":00+00:00")
        candles = self.load_fixture(HEADER, SECOND_ROW, offset_row)
        self.assertEqual([candle["timestamp"] for candle in candles], EXPECTED_TIMES[:2])

    def test_duplicate_minute_is_rejected_even_with_different_utc_spelling(self) -> None:
        with self.assertRaises(HistoryDataError):
            self.load_fixture(HEADER, FIRST_ROW, FIRST_ROW.replace(":00Z", ":00+00:00"))

    def test_invalid_timestamps_are_rejected(self) -> None:
        for timestamp in (
            "invalid",
            "2026-02-30T14:30:00Z",
            "2026-11-09T14:30:01Z",
            "2026-11-09T14:30:00-05:00",
            "2026-11-09T14:30:00",
        ):
            with self.subTest(timestamp=timestamp), self.assertRaises(HistoryDataError):
                self.load_fixture(HEADER, f"{timestamp},100,103,99,102,1200")

    def test_invalid_prices_are_rejected(self) -> None:
        for price in ("", "invalid", "NaN", "inf", "-inf", "1e400"):
            with self.subTest(price=price), self.assertRaises(HistoryDataError):
                self.load_fixture(HEADER, FIRST_ROW.replace(",100,", f",{price},"))

    def test_invalid_volumes_are_rejected(self) -> None:
        for volume in ("", "-1", "1.5", "1.0", "1e3"):
            with self.subTest(volume=volume), self.assertRaises(HistoryDataError):
                self.load_fixture(HEADER, FIRST_ROW.replace(",1200", f",{volume}"))

    def test_impossible_ohlc_relationships_are_rejected(self) -> None:
        for prices in (
            "104,103,99,102",
            "100,101,99,102",
            "100,103,101,102",
            "100,103,99,98",
            "101,100,102,101",
        ):
            with self.subTest(prices=prices), self.assertRaises(HistoryDataError):
                self.load_fixture(HEADER, f"2026-11-09T14:30:00Z,{prices},1200")

    def test_missing_unexpected_and_reordered_headers_are_rejected(self) -> None:
        for header in (
            HEADER.removesuffix(",volume"),
            HEADER + ",extra",
            HEADER.replace("open,high", "high,open"),
        ):
            with self.subTest(header=header), self.assertRaises(HistoryDataError):
                self.load_fixture(header, FIRST_ROW)

    def test_missing_and_additional_row_fields_are_rejected(self) -> None:
        for row in (FIRST_ROW.removesuffix(",1200"), FIRST_ROW + ",extra"):
            with self.subTest(row=row), self.assertRaises(HistoryDataError):
                self.load_fixture(HEADER, row)


class HistoryRouteTest(unittest.IsolatedAsyncioTestCase):
    async def test_route_returns_exact_fields_and_json_types(self) -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            response = await client.get("/api/history", params={"as_of": "2026-11-09T21:00:00Z"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "application/json")
        envelope = response.json()
        self.assertEqual(set(envelope), {"symbol", "interval", "as_of", "candles", "metadata"})
        self.assertEqual((envelope["symbol"], envelope["interval"], envelope["as_of"]),
                         ("AAPL", "1m", "2026-11-09T21:00:00Z"))
        self.assertEqual(envelope["metadata"], [
            {"timestamp": timestamp, "coverage": "full", "observed_minutes": 1,
             "expected_minutes": 1, "is_complete": True} for timestamp in EXPECTED_TIMES
        ])
        candles = envelope["candles"]
        self.assertEqual([candle["timestamp"] for candle in candles], EXPECTED_TIMES)
        self.assertEqual(candles[1], SECOND_CANDLE)
        for candle in candles:
            self.assertEqual(set(candle), set(SECOND_CANDLE))
            self.assertIs(type(candle["timestamp"]), str)
            self.assertIs(type(candle["volume"]), int)
            for field in ("open", "high", "low", "close"):
                self.assertIn(type(candle[field]), (int, float))

    async def test_missing_or_malformed_file_returns_safe_error(self) -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            with TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as directory:
                path = Path(directory) / "internal-candles.csv"
                with patch("app.main.HISTORY_FILE", path):
                    missing = await client.get("/api/history")
                    path.write_text("private-file-content", encoding="utf-8")
                    malformed = await client.get("/api/history")

        for response in (missing, malformed):
            self.assertEqual(response.status_code, 500)
            self.assertEqual(
                response.json(), {"detail": "Historical candle data is unavailable."}
            )

    async def test_interval_options_and_fixture_cutoff(self) -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            for interval, expected in (("1m", 1), ("5m", 5), ("15m", 15), ("1h", 60), ("1d", 390)):
                with self.subTest(interval=interval):
                    response = await client.get("/api/history", params={
                        "symbol": "AAPL", "interval": interval, "as_of": "2026-11-09T14:32:30Z",
                    })
                    self.assertEqual(response.status_code, 200)
                    result = response.json()
                    self.assertEqual(result["interval"], interval)
                    self.assertEqual(result["metadata"][0]["expected_minutes"], expected)
                    self.assertEqual(result["metadata"][0]["observed_minutes"], 1 if interval == "1m" else 2)
                    self.assertEqual(result["candles"][-1]["close"], 101)
                    self.assertNotIn("2026-11-09T14:32:00Z", [row["timestamp"] for row in result["candles"]])

    async def test_invalid_queries_return_bounded_errors(self) -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            for params, detail in (
                ({"symbol": "MSFT"}, "Unsupported symbol."),
                ({"interval": "2m"}, "Unsupported interval."),
                ({"bogus": "x" * 256}, "Invalid history query parameters."),
                ([("interval", "1m"), ("interval", "5m")], "Invalid history query parameters."),
            ):
                with self.subTest(params=params):
                    response = await client.get("/api/history", params=params)
                    self.assertEqual(response.status_code, 422)
                    self.assertEqual(response.json(), {"detail": detail})
            for value in ("", "2026-11-09", "2026-02-30T00:00:00Z", "2026-11-09T14:30:00-05:00",
                          "9999-12-31T23:59:59Z", "1900-01-01T00:00:00Z"):
                with self.subTest(as_of=value):
                    response = await client.get("/api/history", params={"as_of": value})
                    self.assertEqual(response.status_code, 422)
                    self.assertEqual(response.json(), {
                        "detail": "as_of must be a supported UTC timestamp at or before now.",
                    })
