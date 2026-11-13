<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { CandlestickSeries, createChart, HistogramSeries } from 'lightweight-charts'
import { intervals, symbol, useMarketFeed } from '../marketFeed.js'
import { useReplayFeed } from '../replayFeed.js'
import ReplayControls from './ReplayControls.vue'

const props = defineProps({ replay: Boolean })
const chartHost = ref(null)
const candles = ref([])
const selected = ref(null)
const replay = props.replay ? useReplayFeed() : null
const {
  interval, historyState, transport, feed, source, snapshot, upsert, retry,
} = replay ?? useMarketFeed()
const upColor = '#087f72'
const downColor = '#b84045'
const volumeFormat = new Intl.NumberFormat('en-US')
const dateFormat = new Intl.DateTimeFormat('en-GB', {
  day: 'numeric',
  month: 'long',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
  timeZone: 'UTC',
})
let chart
let priceSeries
let volumeSeries
let rowsByTime = new Map()

const sourceNames = {
  synthetic_csv: 'Synthetic CSV',
  yahoo_finance: 'Yahoo Finance',
  constructed_test: 'Constructed test data',
}
const dataModes = { synthetic: 'Synthetic', recorded: 'Recorded', live: 'Live', replay: 'Replay' }
const transportLabels = { connecting: 'Connecting', connected: 'Connected', disconnected: 'Disconnected' }
const feedLabels = {
  connecting: 'Connecting',
  live: 'Live',
  stale: 'Stale',
  unavailable: 'Unavailable',
  recorded: 'Recorded input',
}
const heading = computed(() => {
  if (replay) return 'Replay'
  if (source.value?.mode === 'synthetic') {
    return interval.value === '1m' ? 'Synthetic one-minute sample' : 'Synthetic sample'
  }
  return 'Market candles'
})
const feedStatus = computed(() => {
  if (replay?.available.value === true) return 'Recorded session — live feed off'
  if (replay?.available.value === false) return 'Replay unavailable with a feed active'
  return transport.value === 'connected' ? feedLabels[feed.value?.feed_status] : 'Unknown'
})
const sourceAge = computed(() => (
  Number.isFinite(feed.value?.age_seconds) ? `${Math.round(feed.value.age_seconds)} s` : 'Unavailable'
))
const volumeUnit = computed(() => (
  source.value?.name === 'synthetic_csv' || source.value?.volumeUnit === 'shares' ? ' shares' : ''
))

function utcLabel(seconds) {
  return `${dateFormat.format(seconds * 1000)} UTC`
}

function inspectFromChart({ time, sourceEvent }) {
  // Layout can reproject the crosshair without a mouse or touch interaction.
  if (!sourceEvent) return
  const candle = rowsByTime.get(time)
  if (candle) selected.value = candle
}

function inspectFromSelect(event) {
  const candle = rowsByTime.get(Number(event.target.value))
  if (!candle) return
  selected.value = candle
  chart.setCrosshairPosition(candle.close, candle.time, priceSeries)
}

function ensureChart() {
  if (chart) return
  chart = createChart(chartHost.value, {
    autoSize: true,
    layout: {
      attributionLogo: false,
      textColor: '#365354',
      panes: { separatorColor: '#d6e5e1', enableResize: false },
    },
    grid: {
      vertLines: { color: '#eaf1ef' },
      horzLines: { color: '#eaf1ef' },
    },
    localization: { timeFormatter: utcLabel },
    timeScale: { timeVisible: true, secondsVisible: false, maxBarSpacing: 96 },
  })
  priceSeries = chart.addSeries(CandlestickSeries, {
    upColor,
    downColor,
    wickUpColor: upColor,
    wickDownColor: downColor,
    borderVisible: false,
    priceLineVisible: false,
  })
  volumeSeries = chart.addSeries(HistogramSeries, {
    color: '#638ca5',
    priceFormat: { type: 'volume' },
    priceLineVisible: false,
  }, 1)
  chart.panes()[0].setStretchFactor(3)
  chart.panes()[1].setStretchFactor(1)
  chart.subscribeCrosshairMove(inspectFromChart)
}

function chartRow({ timestamp, ...values }, metadata) {
  return { ...values, time: Date.parse(timestamp) / 1000, metadata }
}

function pricePoint({ time, open, high, low, close }) {
  return { time, open, high, low, close }
}

function volumePoint({ time, volume }) {
  return volume === null ? { time } : { time, value: volume }
}

function setSeries(data) {
  priceSeries.setData(data.map(pricePoint))
  volumeSeries.setData(data.map(volumePoint))
}

watch(snapshot, (history) => {
  const metadata = new Map(history?.metadata?.map((item) => [item.timestamp, item]))
  const data = history?.candles.map((row) => chartRow(row, metadata.get(row.timestamp))) ?? []
  const hadData = candles.value.length > 0
  rowsByTime = new Map(data.map((row) => [row.time, row]))
  candles.value = data
  selected.value = rowsByTime.get(selected.value?.time) ?? data[0] ?? null
  if (data.length) ensureChart()
  if (chart) {
    setSeries(data)
    if (!hadData && data.length) chart.timeScale().fitContent()
  }
}, { flush: 'sync' })

if (upsert) watch(upsert, (event) => {
  if (!event) return
  ensureChart()
  const row = chartRow(event.candle, event.metadata)
  const last = candles.value.at(-1)
  rowsByTime.set(row.time, row)
  candles.value = [...rowsByTime.values()].sort((left, right) => left.time - right.time)
  if (selected.value?.time === row.time || !selected.value) selected.value = row
  if (!last || row.time >= last.time) {
    priceSeries.update(pricePoint(row))
    volumeSeries.update(volumePoint(row))
  } else {
    // A late or revised observation may change a bucket before the latest one.
    setSeries(candles.value)
  }
  if (!last) chart.timeScale().fitContent()
}, { flush: 'sync' })

onBeforeUnmount(() => chart?.remove())
</script>

<template>
  <section aria-labelledby="history-heading" class="history">
    <h2 id="history-heading">{{ heading }}</h2>
    <ReplayControls v-if="replay" :controls="replay" />
    <div class="timeframe">
      <label for="market-timeframe">Timeframe</label>
      <select id="market-timeframe" v-model="interval" :disabled="!!replay" :aria-describedby="replay ? 'replay-timeframe' : null">
        <option v-for="value in intervals" :key="value" :value="value">{{ value }}</option>
      </select>
      <p v-if="replay" id="replay-timeframe" class="axis-label">Replay uses one-minute candles. Switch back to market candles to change the timeframe.</p>
    </div>
    <dl aria-label="Market feed" class="feed-details" :aria-live="replay ? null : 'polite'">
      <div><dt>Symbol</dt><dd>{{ replay ? (replay.recording.value?.symbol ?? 'Unavailable') : symbol }}</dd></div>
      <div><dt>Interval</dt><dd>{{ interval }}</dd></div>
      <div><dt>Source</dt><dd>{{ sourceNames[source?.name] ?? source?.name ?? 'Unavailable' }}</dd></div>
      <div><dt>Data mode</dt><dd>{{ dataModes[source?.mode] ?? 'Unavailable' }}</dd></div>
      <div><dt>Feed status</dt><dd>{{ feedStatus }}</dd></div>
      <div><dt>WebSocket</dt><dd>{{ transportLabels[transport] }}</dd></div>
      <template v-if="replay">
        <div><dt>Selected UTC range</dt><dd>{{ replay.start.value || 'Unavailable' }} to {{ replay.end.value || 'Unavailable' }}</dd></div>
        <div><dt>Playback speed</dt><dd>{{ replay.activeSpeed.value }}×</dd></div>
        <div><dt>Original source time (UTC)</dt><dd>{{ feed?.source_time ?? 'Unavailable' }}</dd></div>
        <div><dt>Original receipt time (UTC)</dt><dd>{{ feed?.receipt_time ?? 'Unavailable' }}</dd></div>
      </template>
      <template v-else>
        <div><dt>Source age</dt><dd>{{ sourceAge }}</dd></div>
        <div><dt>Latest source time (UTC)</dt><dd>{{ feed?.latest_source_time ?? 'Unavailable' }}</dd></div>
        <div><dt>Update source time (UTC)</dt><dd>{{ feed?.source_time ?? 'Unavailable' }}</dd></div>
        <div><dt>Backend receipt time (UTC)</dt><dd>{{ feed?.receipt_time ?? 'Unavailable' }}</dd></div>
      </template>
      <div><dt>Observation ID</dt><dd>{{ feed?.observation_id ?? 'Unavailable' }}</dd></div>
    </dl>
    <button v-if="!replay && transport === 'disconnected'" type="button" @click="retry">Reconnect feed</button>
    <p class="axis-label">Price and volume{{ volumeUnit ? ' (shares)' : '' }} · UTC</p>
    <p v-if="historyState" aria-live="polite">{{ historyState }}</p>
    <div ref="chartHost" class="chart" role="img" aria-label="Candlestick price and volume chart" />

    <template v-if="selected">
      <label for="inspect-candle">Inspect candle (UTC)</label>
      <select id="inspect-candle" :value="selected.time" @change="inspectFromSelect">
        <option v-for="candle in candles" :key="candle.time" :value="candle.time">
          {{ utcLabel(candle.time) }}
        </option>
      </select>
      <dl aria-label="Selected candle">
        <div><dt>Open</dt><dd>{{ selected.open }}</dd></div>
        <div><dt>High</dt><dd>{{ selected.high }}</dd></div>
        <div><dt>Low</dt><dd>{{ selected.low }}</dd></div>
        <div><dt>Close</dt><dd>{{ selected.close }}</dd></div>
        <div>
          <dt>Volume</dt>
          <dd>{{ selected.volume === null ? 'Unavailable' : `${volumeFormat.format(selected.volume)}${volumeUnit}` }}</dd>
        </div>
      </dl>
      <dl v-if="selected.metadata" aria-label="Selected candle status">
        <div>
          <dt>Candle status</dt>
          <dd>{{ selected.metadata.is_complete ? 'Complete' : 'Forming' }}</dd>
        </div>
        <div>
          <dt>Coverage</dt>
          <dd>{{ selected.metadata.coverage === 'full' ? 'Full' : 'Partial' }}
            ({{ selected.metadata.observed_minutes }}/{{ selected.metadata.expected_minutes }} minutes)</dd>
        </div>
      </dl>
    </template>

    <footer>
      TradingView Lightweight Charts™ · Copyright (с) 2025 TradingView, Inc.
      <a href="https://www.tradingview.com/">TradingView</a>
    </footer>
  </section>
</template>

<style scoped>
.history {
  margin-top: 2rem;
  padding: clamp(0.85rem, 3vw, 1.5rem);
  border: 1px solid #d6e5e1;
  border-radius: 0.65rem;
  background: #fff;
}

h2 {
  margin: 0;
}

.timeframe {
  margin-top: 1rem;
}

.feed-details {
  font-size: 0.875rem;
}

.axis-label,
footer {
  color: #365354;
  font-size: 0.875rem;
}

.chart {
  height: 21rem;
  margin-bottom: 1rem;
}

label {
  display: block;
  margin-bottom: 0.35rem;
  font-weight: 600;
}

select {
  max-width: 100%;
  padding: 0.4rem;
  border: 1px solid #769491;
  border-radius: 0.3rem;
  font: inherit;
}

dl {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem 1.5rem;
}

dd {
  margin: 0;
  font-weight: 600;
}

a {
  color: #14595b;
}
</style>
