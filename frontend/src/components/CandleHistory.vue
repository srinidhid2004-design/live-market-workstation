<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { CandlestickSeries, createChart, HistogramSeries } from 'lightweight-charts'

const chartHost = ref(null)
const candles = ref([])
const selected = ref(null)
const state = ref('Loading synthetic candles.')
const request = new AbortController()
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
let rowsByTime

function utcLabel(seconds) {
  return `${dateFormat.format(seconds * 1000)} UTC`
}

function inspectFromChart({ time }) {
  const candle = rowsByTime.get(time)
  if (candle) selected.value = candle
}

function inspectFromSelect(event) {
  const candle = rowsByTime.get(Number(event.target.value))
  if (!candle) return
  selected.value = candle
  chart.setCrosshairPosition(candle.close, candle.time, priceSeries)
}

onMounted(async () => {
  try {
    const response = await fetch('/api/history', {
      cache: 'no-store',
      signal: AbortSignal.any([request.signal, AbortSignal.timeout(5000)]),
    })
    if (!response.ok) throw new Error('History request failed.')

    const rows = await response.json()
    if (request.signal.aborted) return
    if (rows.length === 0) {
      state.value = 'No synthetic candles available.'
      return
    }

    const data = rows.map(({ timestamp, ...values }) => ({
      ...values,
      time: Date.parse(timestamp) / 1000,
    }))
    rowsByTime = new Map(data.map((candle) => [candle.time, candle]))
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
    const volumeSeries = chart.addSeries(HistogramSeries, {
      color: '#638ca5',
      priceFormat: { type: 'volume' },
      priceLineVisible: false,
    }, 1)
    chart.panes()[0].setStretchFactor(3)
    chart.panes()[1].setStretchFactor(1)
    priceSeries.setData(data.map(({ time, open, high, low, close }) => ({
      time, open, high, low, close,
    })))
    volumeSeries.setData(data.map(({ time, volume }) => ({ time, value: volume })))
    chart.timeScale().fitContent()
    chart.subscribeCrosshairMove(inspectFromChart)
    candles.value = data
    selected.value = data[0]
    state.value = ''
  } catch {
    if (!request.signal.aborted) {
      chart?.remove()
      chart = undefined
      state.value = 'Synthetic candle history is unavailable.'
    }
  }
})

onBeforeUnmount(() => {
  request.abort()
  chart?.remove()
})
</script>

<template>
  <section aria-labelledby="history-heading" class="history">
    <h2 id="history-heading">Synthetic one-minute sample</h2>
    <p class="axis-label">Price and volume (shares) · UTC</p>
    <p aria-live="polite" v-if="state">{{ state }}</p>
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
        <div><dt>Volume</dt><dd>{{ volumeFormat.format(selected.volume) }} shares</dd></div>
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
