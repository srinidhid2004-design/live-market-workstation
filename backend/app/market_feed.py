"""Share one persisted observation stream across local AAPL clients."""

import asyncio
from collections.abc import AsyncGenerator, Callable
from contextlib import aclosing
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal, Protocol

from .candles import CandleData, form_candles
from .observations import Observation, ObservationStore, observation_source_time
from .timeframes import SYMBOL, CandleMetadata, HistoryResponse, Interval, aggregate_minutes, utc_text


STALE_SECONDS = 120
FIRST_OBSERVATION_SECONDS = 30
STATUS_SECONDS = 2
MAX_CLIENTS = 16
MAX_CANDLES = 500
MAX_BATCH_UPSERTS = 12

DataMode = Literal["synthetic", "recorded", "live"]
FeedStatus = Literal["connecting", "live", "stale", "unavailable", "recorded"]
Message = dict[str, object]
HistoryLoader = Callable[[Interval, datetime], HistoryResponse]


@dataclass(frozen=True)
class FeedUnavailable:
    """A provider-reported outage. The provider may later supply a new observation."""


class ObservationProvider(Protocol):
    @property
    def source_name(self) -> str: ...

    @property
    def data_mode(self) -> Literal["recorded", "live"]: ...

    @property
    def cumulative_volume_field(self) -> str | None: ...

    def observations(self) -> AsyncGenerator[Observation | FeedUnavailable, None]: ...


@dataclass(eq=False)
class FeedClient:
    interval: Interval
    history: HistoryResponse
    queue: asyncio.Queue[list[Message] | None] = field(default_factory=lambda: asyncio.Queue(maxsize=4))
    needs_snapshot: bool = False


def _candle_rows(history: HistoryResponse) -> dict[str, tuple[CandleData, CandleMetadata]]:
    return {row["timestamp"]: (row, meta) for row, meta in zip(history["candles"], history["metadata"], strict=True)}


async def _finish_store_work[**P, T](work: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
    # Cancelling the await must not leave a SQLite operation running at shutdown.
    task = asyncio.create_task(asyncio.to_thread(work, *args, **kwargs))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        await asyncio.gather(task, return_exceptions=True)
        raise


class MarketFeed:
    def __init__(
        self, *, provider: ObservationProvider | None, store: ObservationStore | None,
        clock: Callable[[], datetime], synthetic_history: HistoryLoader,
    ) -> None:
        self.provider = provider
        self.store = store
        self.clock = clock
        self.synthetic_history = synthetic_history
        self.source = provider.source_name if provider else "synthetic_csv"
        self.data_mode: DataMode = provider.data_mode if provider else "synthetic"
        self._lock = asyncio.Lock()
        self._clients: set[FeedClient] = set()
        self._tasks: list[asyncio.Task[None]] = []
        self._subscription_read: asyncio.Task[HistoryResponse] | None = None
        self._closed = False
        self._started_at = clock()
        self._phase: FeedStatus = "connecting" if provider else "unavailable"
        self._latest_source_time: datetime | None = None
        self._observation_id: int | None = None
        self._source_time: datetime | None = None
        self._receipt_time: datetime | None = None

    @property
    def client_count(self) -> int:
        return len(self._clients)

    def _restore_context(self) -> None:
        assert self.store is not None
        as_of = self.clock()
        for row in self.store.read():
            if row.source_name != self.source or row.ticker != SYMBOL:
                continue
            source_time = datetime.fromisoformat(row.source_time_utc)
            receipt_time = datetime.fromisoformat(row.receipt_time_utc)
            if source_time <= as_of and receipt_time <= as_of:
                self._remember(row.observation_id, source_time, receipt_time)

    def _remember(self, observation_id: int, source_time: datetime, receipt_time: datetime) -> None:
        self._observation_id = observation_id
        self._source_time = source_time
        self._receipt_time = receipt_time.astimezone(UTC)
        if self._latest_source_time is None or source_time > self._latest_source_time:
            self._latest_source_time = source_time

    async def start(self) -> None:
        if self._closed or self._tasks:
            raise RuntimeError("Market feed already started or closed.")
        if self.store is not None:
            await _finish_store_work(self._restore_context)
        self._started_at = self.clock()
        self._tasks.append(asyncio.create_task(self._heartbeat()))
        if self.provider is not None:
            self._tasks.append(asyncio.create_task(self._consume(self.provider)))

    async def stop(self) -> None:
        self._closed = True
        for client in self._clients:
            self._replace_queue(client, None)
        self._clients.clear()
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        if self._subscription_read is not None:
            await asyncio.gather(self._subscription_read, return_exceptions=True)

    def _minutes(self, as_of: datetime) -> list[CandleData]:
        assert self.store is not None and self.provider is not None
        return [candle.data for candle in form_candles(
            self.store, source_name=self.source, ticker=SYMBOL, evaluated_at=as_of, as_of=as_of,
            cumulative_volume_field=self.provider.cumulative_volume_field,
        )]

    def _history(self, interval: Interval, as_of: datetime) -> HistoryResponse:
        if self.store is None:
            return self.synthetic_history(interval, as_of)
        return self._aggregate(self._minutes(as_of), interval, as_of)

    @staticmethod
    def _aggregate(minutes: list[CandleData], interval: Interval, as_of: datetime) -> HistoryResponse:
        history = aggregate_minutes(minutes, interval=interval, as_of=as_of)
        history["candles"] = history["candles"][-MAX_CANDLES:]
        history["metadata"] = history["metadata"][-MAX_CANDLES:]
        return history

    async def history(self, interval: Interval, as_of: datetime) -> HistoryResponse:
        async with self._lock:
            return await _finish_store_work(self._history, interval, as_of)

    def context(self, interval: Interval | None, as_of: datetime) -> Message:
        age = None
        if self._latest_source_time is not None:
            age = max(0, int((as_of - self._latest_source_time).total_seconds()))
        status = self._phase
        if status == "connecting" and (as_of - self._started_at).total_seconds() >= FIRST_OBSERVATION_SECONDS:
            status = "unavailable"
        elif status == "live" and age is not None and age >= STALE_SECONDS:
            status = "stale"
        return {
            "version": 1, "symbol": SYMBOL, "interval": interval,
            "source": self.source, "data_mode": self.data_mode,
            "backend_status": "connected", "feed_status": status,
            "source_time": utc_text(self._source_time) if self._source_time else None,
            "receipt_time": utc_text(self._receipt_time) if self._receipt_time else None,
            "latest_source_time": utc_text(self._latest_source_time) if self._latest_source_time else None,
            "age_seconds": age, "as_of": utc_text(as_of), "observation_id": self._observation_id,
        }

    def _snapshot(self, history: HistoryResponse, as_of: datetime) -> Message:
        return {
            **self.context(history["interval"], as_of), "type": "snapshot",
            "candles": history["candles"], "metadata": history["metadata"],
        }

    async def subscribe(self, interval: Interval) -> FeedClient | None:
        async with self._lock:
            if self._closed or len(self._clients) >= MAX_CLIENTS or self._subscription_read is not None:
                return None
            as_of = self.clock()
            read = asyncio.create_task(asyncio.to_thread(self._history, interval, as_of))
            self._subscription_read = read
            read.add_done_callback(self._finish_subscription_read)
            # A socket deadline may end the wait while SQLite is still closing its read.
            history = await asyncio.shield(read)
            if self._closed:
                return None
            client = FeedClient(interval, history)
            client.queue.put_nowait([self._snapshot(history, as_of)])
            self._clients.add(client)
            return client

    def _finish_subscription_read(self, read: asyncio.Task[HistoryResponse]) -> None:
        self._subscription_read = None
        if not read.cancelled():
            read.exception()

    def unsubscribe(self, client: FeedClient) -> None:
        self._clients.discard(client)

    @staticmethod
    def _replace_queue(client: FeedClient, messages: list[Message] | None) -> None:
        while not client.queue.empty():
            client.queue.get_nowait()
        client.queue.put_nowait(messages)

    async def refresh(self) -> None:
        """Publish elapsed completion boundaries and current feed status."""
        async with self._lock:
            await self._publish(self.clock())

    def _snapshots(self, intervals: set[Interval], as_of: datetime) -> dict[Interval, HistoryResponse]:
        if self.store is None:
            return {interval: self.synthetic_history(interval, as_of) for interval in intervals}
        minutes = self._minutes(as_of)
        return {interval: self._aggregate(minutes, interval, as_of) for interval in intervals}

    async def _publish(self, as_of: datetime) -> None:
        if self._closed or not self._clients:
            return
        intervals = {client.interval for client in self._clients}
        try:
            snapshots = await _finish_store_work(self._snapshots, intervals, as_of)
        except Exception:
            for client in self._clients:
                client.needs_snapshot = True
                self._replace_queue(client, [{
                    **self.context(client.interval, as_of), "type": "error",
                    "code": "history_unavailable", "message": "Market history is unavailable.",
                }])
            return
        for client in self._clients:
            history = snapshots[client.interval]
            before, after = _candle_rows(client.history), _candle_rows(history)
            changes = [(row, meta) for stamp, (row, meta) in after.items() if before.get(stamp) != (row, meta)]
            client.history = history
            if client.queue.full() or client.needs_snapshot:
                client.needs_snapshot = False
                self._replace_queue(client, [self._snapshot(history, as_of)])
            elif before.keys() - after.keys() or len(changes) > MAX_BATCH_UPSERTS:
                client.queue.put_nowait([self._snapshot(history, as_of)])
            else:
                context = self.context(client.interval, as_of)
                client.queue.put_nowait([
                    {**context, "type": "candle_upsert", "candle": row, "metadata": meta}
                    for row, meta in changes
                ] or [{**context, "type": "feed_status"}])

    async def _heartbeat(self) -> None:
        while True:
            await asyncio.sleep(STATUS_SECONDS)
            await self.refresh()

    async def _unavailable(self) -> None:
        async with self._lock:
            self._phase = "unavailable"
            await self._publish(self.clock())

    async def _consume(self, provider: ObservationProvider) -> None:
        assert self.store is not None
        try:
            async with aclosing(provider.observations()) as observations:
                async for observation in observations:
                    if isinstance(observation, FeedUnavailable):
                        await self._unavailable()
                        continue
                    if observation.ticker != SYMBOL or observation.source_name != self.source:
                        continue
                    async with self._lock:
                        try:
                            source_time = observation_source_time(observation)
                            receipt_offset = observation.received_at.utcoffset()
                            if receipt_offset is None or max(source_time, observation.received_at) > self.clock():
                                continue
                            result = await _finish_store_work(self.store.record, observation)
                        except ValueError:
                            continue
                        phase = "recorded" if self.data_mode == "recorded" else "live"
                        recovered = self._phase != phase
                        self._phase = phase
                        if result.inserted:
                            self._remember(result.observation_id, source_time, observation.received_at)
                        if result.inserted or recovered:
                            await self._publish(self.clock())
        except Exception:
            await self._unavailable()
        else:
            await self._unavailable()
