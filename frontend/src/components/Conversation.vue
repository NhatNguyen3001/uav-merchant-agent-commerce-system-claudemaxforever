<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import Chevron from './Chevron.vue'
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
  pipelineVisible: Boolean,
})
const emit = defineEmits(['run', 'replay', 'delete', 'clear', 'show-pipeline'])

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
      <div class="brand-lockup">
        <img class="brand-mark" src="/logo-mark.png" alt="" />
        <div>
          <h1>MACS</h1>
          <p class="brand-sub">The merchant's agent for AI shoppers</p>
        </div>
      </div>
      <div class="brand-actions">
        <button v-if="!pipelineVisible" type="button" class="ghost" @click="emit('show-pipeline')">Show pipeline</button>
        <button type="button" class="ghost" :aria-expanded="drawerOpen" @click="drawerOpen = !drawerOpen">
          Merchant rules
          <Chevron :open="drawerOpen" />
        </button>
      </div>
    </header>

    <form v-if="drawerOpen && rules" class="drawer" @submit.prevent="onSave">
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

    <div class="thread-wrap scroll">
      <div v-if="!bubbles.length && !running" class="thread-empty">
        <p><strong>You play the buyer's AI agent.</strong> Type what it would ask the store, pick an identity, and run.</p>
        <p><strong>MACS answers as the merchant.</strong> It verifies the agent, decodes what the buyer needs, composes a bundle from the catalogue, negotiates within the merchant's rules, and places the order.</p>
        <p>Every step behind the reply appears in the pipeline on the right.</p>
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
