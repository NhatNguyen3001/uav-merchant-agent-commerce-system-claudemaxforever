<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import Composer from './Composer.vue'
import HistoryPanel from './HistoryPanel.vue'
import { fetchRules, saveRules } from '../composables/useRun.js'

const props = defineProps({
  messages: { type: Array, required: true },
  draft: Object,
  runs: { type: Array, required: true },
  runId: String,
  running: Boolean,
  error: String,
})
const emit = defineEmits(['run', 'replay', 'delete', 'clear'])

const rules = ref(null)
const drawerOpen = ref(false)
const saveState = ref('')
const thread = ref(null)

onMounted(async () => {
  rules.value = await fetchRules()
})

async function onSave() {
  saveState.value = 'Saving'
  await saveRules(rules.value)
  saveState.value = 'Saved'
  setTimeout(() => (saveState.value = ''), 1500)
}

// The typed query shows at once; once the backend echoes it as the first buyer message, the echo takes over.
const bubbles = computed(() => {
  const list = props.messages.map((e) => ({ id: e.id, from: e.payload.from, text: e.payload.text, ts: e.ts }))
  if (props.draft && !list.some((m) => m.from === 'buyer_agent')) {
    list.unshift({ id: 'draft', from: 'buyer_agent', text: props.draft.text, ts: null })
  }
  return list
})

const waiting = computed(() => props.running && (bubbles.value.length === 0 || bubbles.value[bubbles.value.length - 1].from === 'buyer_agent'))

watch(
  () => [bubbles.value.length, waiting.value],
  async () => {
    await nextTick()
    thread.value?.lastElementChild?.scrollIntoView({ block: 'end', behavior: 'smooth' })
  },
)

function time(ts) {
  if (!ts) return ''
  const d = new Date(ts)
  return isNaN(d) ? '' : d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}
</script>

<template>
  <aside class="panel">
    <header class="brand">
      <h1>MACS</h1>
      <button class="icon" type="button" :aria-expanded="drawerOpen" aria-label="Merchant rules" @click="drawerOpen = !drawerOpen">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
          <circle cx="8" cy="8" r="2.2" /><path d="M8 1.5v2M8 12.5v2M1.5 8h2M12.5 8h2M3.4 3.4l1.4 1.4M11.2 11.2l1.4 1.4M3.4 12.6l1.4-1.4M11.2 4.8l1.4-1.4" />
        </svg>
      </button>
    </header>

    <form v-if="drawerOpen && rules" class="drawer" @submit.prevent="onSave">
      <p class="drawer-title">Merchant rules</p>
      <p class="drawer-note">Hard limits are enforced by the gates and never shown to the model.</p>
      <label>Max discount %<input type="number" v-model.number="rules.hard.max_discount_pct" min="0" max="90" /></label>
      <label>Min margin %<input type="number" v-model.number="rules.hard.min_margin_pct" min="0" max="90" /></label>
      <label>Negotiation style<input v-model="rules.soft.negotiation_style" /></label>
      <div class="drawer-actions">
        <button class="primary" type="submit">Save rules</button>
        <span class="status">{{ saveState }}</span>
      </div>
    </form>

    <HistoryPanel :runs="runs" :run-id="runId" :running="running" @replay="emit('replay', $event)" @delete="emit('delete', $event)" @clear="emit('clear')" />

    <div class="thread-wrap">
      <div v-if="!bubbles.length && !running" class="thread-empty">
        <p>Type what an incoming shopping agent would say, and watch the merchant agent answer it.</p>
        <p>The pipeline on the right shows every gate, tool call, and proposal behind the reply.</p>
      </div>
      <ol ref="thread" class="thread">
        <li v-for="m in bubbles" :key="m.id" :class="['bubble', m.from]">
          <p class="bubble-who">{{ m.from === 'buyer_agent' ? "Buyer's agent" : 'Merchant agent' }}<span v-if="m.ts" class="bubble-time">{{ time(m.ts) }}</span></p>
          <p class="bubble-text">{{ m.text }}</p>
        </li>
        <li v-if="waiting" class="bubble merchant_agent typing" aria-live="polite">
          <span class="dots"><i></i><i></i><i></i></span>
        </li>
      </ol>
    </div>

    <Composer :running="running" :error="error" @run="emit('run', $event)" />
  </aside>
</template>
