<script setup>
import { computed, ref, watch } from 'vue'
import Chevron from './Chevron.vue'
import { money } from '../format.js'

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

const SCENARIO_TITLE = {
  happy_path: 'Podcast starter',
  instant_buyer: 'Gym earbuds, no haggling',
  rejected_agent: 'Unregistered agent',
}

function title(r) {
  const named = SCENARIO_TITLE[r.scenario]
  if (r.is_golden) return `Example: ${(named || r.scenario).toLowerCase()}`
  if (r.query) return r.query
  return named || r.scenario
}

function outcome(r) {
  const s = r.summary || {}
  if (r.status === 'running') return { cls: 'running', text: 'Running' }
  if (r.status === 'failed') return { cls: 'failed', text: 'Failed' }
  if (r.status === 'interrupted') return { cls: 'interrupted', text: 'Interrupted' }
  if (s.order_status === 'placed') return { cls: 'placed', text: `Order placed${s.bundle_price != null ? ' · ' + money(s.bundle_price) : ''}` }
  return { cls: 'blocked', text: 'No order' }
}
</script>

<template>
  <section class="history" :class="{ open }">
    <div class="history-bar">
      <button type="button" class="history-toggle" :aria-expanded="open" @click="open = !open">
        <span>History</span>
        <span class="count">{{ runs.length }}</span>
        <Chevron :open="open" />
      </button>
      <button v-if="open && own.length" type="button" class="link" @click="emit('clear')">Clear mine</button>
    </div>
    <div v-if="open" class="history-body scroll">
      <p v-if="!runs.length" class="empty">No runs yet.</p>
      <ul>
        <li v-for="r in [...golden, ...own]" :key="r.run_id" class="run-row" :class="{ current: r.run_id === runId }">
          <button type="button" class="run" :disabled="running" @click="emit('replay', r.run_id)">
            <span class="run-title">{{ title(r) }}</span>
            <span class="run-meta"><span>{{ when(r) }}</span><span :class="outcome(r).cls">{{ outcome(r).text }}</span></span>
          </button>
          <button v-if="!r.is_golden" type="button" class="icon small" :disabled="running" aria-label="Delete this run" title="Delete" @click="emit('delete', r.run_id)">
            <svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="M3 4h10M6.5 4V2.5h3V4M4.5 4l.7 9.5h5.6L11.5 4M6.7 6.5v5M9.3 6.5v5" /></svg>
          </button>
        </li>
      </ul>
    </div>
  </section>
</template>
