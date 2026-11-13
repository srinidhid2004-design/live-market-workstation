<script setup>
const props = defineProps({ controls: { type: Object, required: true } })
const {
  recordings, recording, recordingIndex, start, end, speed, speeds, state, status, pending,
  selectionLocked, canStart, canReset, startReplay, send,
} = props.controls

function recordingLabel(item) {
  const source = item.source === 'constructed_test' ? 'Constructed test data' : item.source
  return `${item.symbol} · ${source}`
}
</script>

<template>
  <form v-if="recordings.length" class="replay-form" @submit.prevent="startReplay">
    <div class="replay-selection">
      <label>
        Recorded symbol and source
        <select v-model="recordingIndex" :disabled="selectionLocked">
          <option v-for="(item, index) in recordings" :key="index" :value="index">
            {{ recordingLabel(item) }}
          </option>
        </select>
      </label>
      <label>
        Start (UTC)
        <input v-model="start" :disabled="selectionLocked" type="text" required maxlength="32" aria-describedby="replay-range-help" spellcheck="false" autocomplete="off">
      </label>
      <label>
        End (UTC)
        <input v-model="end" :disabled="selectionLocked" type="text" required maxlength="32" aria-describedby="replay-range-help" spellcheck="false" autocomplete="off">
      </label>
    </div>
    <p v-if="recording" class="replay-help">Recorded coverage {{ recording.start }} to {{ recording.end }}</p>
    <p id="replay-range-help" class="replay-help">Enter UTC receipt times like 2026-11-09T14:30:00Z. Choose up to 24 hours. The end time is excluded.</p>
    <div class="replay-actions">
      <label>
        Playback speed
        <select v-model="speed" :disabled="pending || state === 'playing' || state === 'connecting'">
          <option v-for="value in speeds" :key="value" :value="value">{{ value }}×</option>
        </select>
      </label>
      <button v-if="state === 'playing'" type="button" :disabled="pending" @click="send('pause')">Pause replay</button>
      <button v-else-if="state === 'paused'" type="button" :disabled="pending" @click="send('play')">Resume replay</button>
      <button v-else type="submit" :disabled="!canStart">Start replay</button>
      <button type="button" :disabled="!canReset" @click="send('reset')">Reset replay</button>
    </div>
  </form>
  <p role="status" aria-label="Replay status">{{ status }}</p>
</template>

<style scoped>
.replay-form {
  margin: 1rem 0;
}

.replay-selection,
.replay-actions {
  display: flex;
  align-items: end;
  flex-wrap: wrap;
  gap: 0.65rem 1rem;
}

label {
  display: grid;
  gap: 0.35rem;
  max-width: 100%;
  font-weight: 600;
}

input,
select {
  padding: 0.4rem;
  border: 1px solid #769491;
  border-radius: 0.3rem;
  font: inherit;
}

input {
  box-sizing: border-box;
  width: 20rem;
  max-width: 100%;
}

.replay-help {
  margin: 0.55rem 0;
  color: #365354;
  font-size: 0.875rem;
  overflow-wrap: anywhere;
}
</style>
