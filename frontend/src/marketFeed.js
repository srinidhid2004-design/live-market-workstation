import { onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'

export const symbol = 'AAPL'
export const intervals = ['1m', '5m', '15m', '1h', '1d']
const retryDelays = [1000, 2000]
const feedStatuses = ['connecting', 'live', 'stale', 'unavailable', 'recorded']

export function useMarketFeed() {
  const interval = ref('1m')
  const historyState = ref('Loading candles.')
  const transport = ref('connecting')
  const feed = shallowRef(null)
  const source = shallowRef(null)
  const snapshot = shallowRef(null)
  const upsert = shallowRef(null)
  let active

  function dispose() {
    const previous = active
    active = undefined
    if (!previous) return
    previous.request.abort()
    clearTimeout(previous.retry)
    clearTimeout(previous.handshake)
    previous.socket?.close()
  }

  function openSocket(subscription, retryIndex = 0) {
    const url = new URL(`/api/market-feed?${subscription.query}`, window.location.href)
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
    const socket = new WebSocket(url)
    subscription.socket = socket
    const isCurrent = () => active === subscription && subscription.socket === socket
    transport.value = 'connecting'
    subscription.handshake = setTimeout(() => socket.close(), 5000)

    socket.addEventListener('message', ({ data }) => {
      if (!isCurrent()) return
      let event
      try {
        event = JSON.parse(data)
      } catch {
        return
      }
      if (event?.version !== 1 || event.symbol !== symbol || event.interval !== subscription.interval) return
      if (!feedStatuses.includes(event.feed_status)) return
      if (event.type === 'snapshot' && (!Array.isArray(event.candles) || !Array.isArray(event.metadata))) return
      if (event.type === 'candle_upsert' && (!event.candle || !event.metadata)) return

      clearTimeout(subscription.handshake)
      transport.value = 'connected'
      feed.value = event
      if (event.type === 'snapshot') {
        source.value = { name: event.source, mode: event.data_mode }
        snapshot.value = event
        historyState.value = event.candles.length ? '' : 'No candles available.'
      } else if (event.type === 'candle_upsert') {
        source.value = { name: event.source, mode: event.data_mode }
        upsert.value = event
        historyState.value = ''
      }
    })

    socket.addEventListener('close', () => {
      if (!isCurrent()) return
      clearTimeout(subscription.handshake)
      transport.value = 'disconnected'
      if (retryIndex < retryDelays.length) {
        subscription.retry = setTimeout(() => openSocket(subscription, retryIndex + 1), retryDelays[retryIndex])
      }
    })
  }

  async function load() {
    dispose()
    const subscription = {
      interval: interval.value,
      query: new URLSearchParams({ symbol, interval: interval.value }),
      request: new AbortController(),
    }
    active = subscription
    snapshot.value = null
    upsert.value = null
    feed.value = null
    source.value = null
    historyState.value = 'Loading candles.'
    transport.value = 'connecting'
    try {
      const response = await fetch(`/api/history?${subscription.query}`, {
        cache: 'no-store',
        signal: AbortSignal.any([subscription.request.signal, AbortSignal.timeout(5000)]),
      })
      if (!response.ok) throw new Error('History request failed.')
      const history = await response.json()
      if (active !== subscription) return
      if (history.symbol !== symbol || history.interval !== subscription.interval || !Array.isArray(history.candles)) {
        throw new Error('Unexpected candle history.')
      }
      source.value = { name: history.source ?? 'synthetic_csv', mode: history.data_mode ?? 'synthetic' }
      snapshot.value = history
      historyState.value = history.candles.length ? '' : 'No candles available.'
    } catch {
      if (active === subscription) historyState.value = 'Candle history is unavailable.'
    }
    if (active === subscription) openSocket(subscription)
  }

  function retry() {
    if (!active || transport.value !== 'disconnected') return
    clearTimeout(active.retry)
    openSocket(active)
  }

  onMounted(load)
  watch(interval, load)
  onBeforeUnmount(dispose)

  return { interval, historyState, transport, feed, source, snapshot, upsert, retry }
}
