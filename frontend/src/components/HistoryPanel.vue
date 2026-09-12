<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({ runs: { type: Array, required: true }, runId: String, running: Boolean })
const emit = defineEmits(['replay', 'delete', 'clear'])

const KEY = 'macs.history.open'
const open = ref(false)
try {
  open.value = localStorage.getItem(KEY) === '1'
} catch (_) {}
watch(open, (v) => {
  try {
    localStorage.setItem(KEY, v ? '1' : '0')
  } catch (_) {}
})

const own = computed(() => props.runs.filter((r) => !r.is_golden))
const golden = computed(() => props.runs.filter((r) => r.is_golden))

function when(r) {
  const d = new Date(r.started_at)
  return isNaN(d) ? '' : d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function title(r) {
  if (r.is_golden) return r.scenario === 'happy_path' ? 'Example: podcast starter' : 'Example: unregistered agent'
  if (r.query) return r.query
  return r.scenario === 'happy_path' ? 'Podcast starter' : r.scenario === 'rejected_agent' ? 'Unregistered agent' : r.scenario
}

function outcome(r) {
  const s = r.summary || {}
  if (r.status === 'running') return 'running'
  if (r.status === 'failed') return 'failed'
  return s.order_status === 'placed' ? `placed ${s.bundle_price ?? ''}` : 'blocked'
}
</script>

<template>
  <section class="history" :class="{ open }">
    <button type="button" class="history-toggle" :aria-expanded="open" @click="open = !open">
      <span class="chev" aria-hidden="true"></span>
      <span>History</span>
      <span class="count">{{ runs.length }}</span>
      <span class="grow"></span>
      <span v-if="open && own.length" class="link" role="button" tabindex="0" @click.stop="emit('clear')" @keydown.enter.stop="emit('clear')">Clear mine</span>
    </button>
    <div v-if="open" class="history-body">
      <p v-if="!runs.length" class="empty">No runs yet.</p>
      <ul>
        <li v-for="r in [...golden, ...own]" :key="r.run_id" class="run-row" :class="{ current: r.run_id === runId }">
          <button type="button" class="run" :disabled="running" @click="emit('replay', r.run_id)">
            <span class="run-title">{{ title(r) }}</span>
            <span class="run-meta"><span>{{ when(r) }}</span><span :class="outcome(r).split(' ')[0]">{{ outcome(r) }}</span></span>
          </button>
          <button v-if="!r.is_golden" type="button" class="icon small" :disabled="running" aria-label="Delete this run" title="Delete" @click="emit('delete', r.run_id)">
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="M3 4h10M6.5 4V2.5h3V4M4.5 4l.7 9.5h5.6L11.5 4M6.7 6.5v5M9.3 6.5v5" /></svg>
          </button>
        </li>
      </ul>
    </div>
  </section>
</template>
