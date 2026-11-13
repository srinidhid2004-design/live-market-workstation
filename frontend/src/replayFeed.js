import { computed, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'

const interval = '1m'
const dayMilliseconds = 86_400_000
const speeds = [1, 2, 4]
const states = ['ready', 'playing', 'paused', 'completed', 'empty', 'failed']
const messages = {
  loading: 'Looking up recorded observations.',
  connecting: 'Opening the recorded session.',
  ready: 'Ready to replay.',
  playing: 'Playing recorded observations.',
  paused: 'Replay paused.',
  completed: 'Replay completed.',
  empty: 'No recorded observations exist for this selection.',
  failed: 'The recorded session could not be replayed.',
}

export function useReplayFeed() {
  const recordings = shallowRef([])
  const available = ref(null)
  const recordingIndex = ref(0)
  const recording = computed(() => recordings.value[recordingIndex.value])
  const start = ref('')
  const end = ref('')
  const speed = ref(1)
  const state = ref('loading')
  const notice = ref('')
  const pending = ref(false)
  const transport = ref('disconnected')
  const feed = shallowRef(null)
  const snapshot = shallowRef(null)
  const source = computed(() => ({ name: recording.value?.source, mode: 'replay', volumeUnit: feed.value?.volume_unit }))
  const status = computed(() => notice.value || messages[state.value])
  const activeSpeed = computed(() => feed.value?.speed ?? speed.value)
  const selectionLocked = computed(() => pending.value || ['connecting', 'playing', 'paused'].includes(state.value))
  const canStart = computed(() => available.value && recording.value && start.value.trim() && end.value.trim() && (
    !selectionLocked.value && ['ready', 'empty', 'failed'].includes(state.value)
  ))
  const canReset = computed(() => !pending.value && transport.value === 'connected' && (
    ['playing', 'paused', 'completed'].includes(state.value)
  ))
  const discovery = new AbortController()
  let active

  function retire() {
    const session = active
    active = undefined
    if (session) {
      clearTimeout(session.deadline)
      session.socket.close()
    }
    transport.value = 'disconnected'
    pending.value = false
  }

  function clearSelection() {
    retire()
    feed.value = null
    snapshot.value = null
    notice.value = ''
    if (recording.value) state.value = 'ready'
  }

  watch(recording, (choice) => {
    if (!choice) return
    // Round a clipped start up so fractional receipt times still fit the 24-hour limit.
    const latestStart = Date.parse(choice.end) - dayMilliseconds + 1
    start.value = Date.parse(choice.start) < latestStart ? new Date(latestStart).toISOString() : choice.start
    end.value = choice.end
  })
  watch([recording, start, end], clearSelection)

  function send(action) {
    if (active?.socket.readyState !== WebSocket.OPEN) return
    pending.value = true
    active.awaiting = action === 'play' ? 'playing' : action === 'pause' ? 'paused' : 'ready'
    active.socket.send(JSON.stringify(action === 'play' ? { action, speed: speed.value } : { action }))
  }

  function openSession() {
    clearSelection()
    const selection = {
      symbol: recording.value.symbol,
      source: recording.value.source,
      start: start.value.trim(),
      end: end.value.trim(),
      interval,
    }
    const url = new URL('/api/replay/stream', window.location.href)
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
    url.search = new URLSearchParams({ ...selection, speed: speed.value })
    const socket = new WebSocket(url)
    const session = { socket, deadline: setTimeout(() => socket.close(), 8000) }
    active = session
    state.value = 'connecting'
    transport.value = 'connecting'

    socket.addEventListener('message', ({ data }) => {
      if (active !== session) return
      let event
      try {
        event = JSON.parse(data)
      } catch {
        return
      }
      if (event?.version !== 1 || event.data_mode !== 'replay' || !states.includes(event.replay_state)) return
      if (event.type === 'error') {
        state.value = 'failed'
        notice.value = event.message || messages.failed
        retire()
        return
      }
      if (!Object.entries(selection).every(([key, value]) => event[key] === value)) return
      if (event.type !== 'snapshot' && event.type !== 'replay_status') return
      if (event.type === 'snapshot' && (!Array.isArray(event.candles) || !Array.isArray(event.metadata))) return

      clearTimeout(session.deadline)
      transport.value = 'connected'
      const shouldPlay = state.value === 'connecting' && event.replay_state === 'ready'
      state.value = event.replay_state
      feed.value = event
      if (event.type === 'snapshot') snapshot.value = event
      if (session.awaiting === event.replay_state || ['completed', 'empty', 'failed'].includes(state.value)) {
        session.awaiting = undefined
        pending.value = false
      }
      if (shouldPlay) send('play')
    })

    socket.addEventListener('close', () => {
      if (active !== session) return
      retire()
      if (!['empty', 'completed', 'failed'].includes(state.value)) {
        state.value = 'failed'
        notice.value = 'The replay connection closed. Start replay again to reconnect.'
      }
    })
  }

  function startReplay() {
    if (!canStart.value) return
    if (transport.value === 'connected' && state.value === 'ready') send('play')
    else openSession()
  }

  async function discover() {
    try {
      const response = await fetch('/api/replay/coverage', {
        cache: 'no-store',
        signal: AbortSignal.any([discovery.signal, AbortSignal.timeout(5000)]),
      })
      if (!response.ok) throw new Error('Replay coverage request failed.')
      const result = await response.json()
      if (discovery.signal.aborted) return
      if (typeof result?.available !== 'boolean' || !Array.isArray(result.recordings)) {
        throw new Error('Unexpected replay coverage.')
      }
      available.value = result.available
      recordings.value = result.recordings
      state.value = recordings.value.length ? 'ready' : 'empty'
      if (!available.value) {
        state.value = 'failed'
        notice.value = 'Restart the backend with its market feed off to use replay.'
      }
    } catch {
      if (discovery.signal.aborted) return
      state.value = 'failed'
      notice.value = 'Recorded observation coverage is unavailable.'
    }
  }

  onMounted(discover)
  onBeforeUnmount(() => {
    discovery.abort()
    retire()
  })

  return {
    interval: ref(interval), feed, source, snapshot, transport,
    available, recordings, recording, recordingIndex, start, end, speed, speeds, state, status, pending,
    activeSpeed, selectionLocked, canStart, canReset, startReplay, send,
  }
}
