"""Deterministic, isolated upstream for the Playwright market feed check."""

import asyncio
import os
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from fastapi import FastAPI

from app.main import create_app
from app.market_feed import FeedUnavailable
from app.observations import UNIX_EPOCH, Observation
from app.timeframes import SYMBOL


START = datetime.fromisoformat("2026-11-09T14:30:00Z")


class DemoSource:
    source_name = "constructed_test"
    data_mode: Literal["recorded"] = "recorded"
    cumulative_volume_field = None

    def __init__(self) -> None:
        self.now = START + timedelta(seconds=10)
        self.events: asyncio.Queue[Observation | FeedUnavailable] = asyncio.Queue(maxsize=8)

    def observation(self, price: int) -> Observation:
        return Observation(
            source_name=self.source_name, ticker=SYMBOL,
            source_timestamp=(self.now - UNIX_EPOCH) // timedelta(seconds=1), source_timestamp_unit="s",
            received_at=self.now, price=price,
        )

    async def observations(self) -> AsyncGenerator[Observation | FeedUnavailable, None]:
        yield self.observation(100)
        while True:
            yield await self.events.get()


def create_demo_app() -> FastAPI:
    provider = DemoSource()
    application = create_app(
        provider=provider, database_path=Path(os.environ["MARKET_FEED_TEST_DB"]), clock=lambda: provider.now,
    )

    @application.post("/api/demo-feed", status_code=202)
    async def action_feed(action: Literal["update", "fail", "recover"]) -> dict[str, bool]:
        if action == "fail":
            event = FeedUnavailable()
        elif action == "update":
            provider.now = START + timedelta(seconds=30)
            event = provider.observation(103)
        else:
            provider.now = START + timedelta(seconds=70)
            event = provider.observation(104)
        await provider.events.put(event)
        return {"accepted": True}

    return application
