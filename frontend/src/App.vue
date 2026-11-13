<script setup>
import { ref } from 'vue'
import CandleHistory from './components/CandleHistory.vue'

const pending = ref(false)
const message = ref('')
const status = ref(null)
const payload = ref('')
const replay = ref(false)

async function checkConnection() {
  if (pending.value) return

  pending.value = true
  message.value = 'Checking connection…'
  status.value = null
  payload.value = ''

  try {
    const response = await fetch('/api/health', {
      cache: 'no-store',
      signal: AbortSignal.timeout(5000),
    })
    status.value = response.status
    if (!response.ok) {
      message.value = 'Backend unavailable. Try again.'
      return
    }

    const result = await response.json()
    if (result?.status !== 'healthy') {
      message.value = 'Backend returned an unexpected health response.'
      return
    }
    payload.value = JSON.stringify({ status: result.status })
    message.value = 'Backend is healthy.'
  } catch {
    message.value = 'Backend unavailable. Try again.'
  } finally {
    pending.value = false
  }
}
</script>

<template>
  <main>
    <h1>Live Market Workstation</h1>
    <p>Local connection check</p>
    <button type="button" :disabled="pending" @click="checkConnection">
      Check connection
    </button>
    <div role="status" aria-atomic="true">
      <p>{{ message }}</p>
      <p v-if="status !== null">HTTP {{ status }}</p>
      <pre v-if="payload">{{ payload }}</pre>
    </div>
    <button class="mode-switch" type="button" @click="replay = !replay">
      {{ replay ? 'Back to market candles' : 'Open replay' }}
    </button>
    <CandleHistory v-if="replay" key="replay" replay />
    <CandleHistory v-else key="market" />
  </main>
</template>

<style>
:root {
  color: #142d30;
  background: #f0f6f5;
  font-family: system-ui, sans-serif;
}

main {
  max-width: 62rem;
  margin: 2rem auto;
  padding: 1.5rem;
}

h1 {
  margin-bottom: 0.25rem;
}

button {
  padding: 0.65rem 1rem;
  color: white;
  background: #14595b;
  border: 0;
  border-radius: 0.4rem;
  font: inherit;
}

button:disabled {
  opacity: 0.65;
}

:focus-visible {
  outline: 3px solid #176e80;
  outline-offset: 3px;
}

.mode-switch {
  margin-top: 0.75rem;
}

pre {
  padding: 0.75rem;
  background: white;
}
</style>
