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
  mobile: Boolean,
  showcase: Boolean,
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
  if (rules.value?.locked) return
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
        <a
          class="icon repo"
          href="https://github.com/NhatNguyen3001/uav-merchant-agent-commerce-system-claudemaxforever"
          target="_blank"
          rel="noopener"
          aria-label="Source code on GitHub"
          title="Source code on GitHub"
        >
          <svg width="18" height="18" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27s1.36.09 2 .27c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8Z" /></svg>
        </a>
        <button v-if="!pipelineVisible && !mobile" type="button" class="ghost" @click="emit('show-pipeline')">Show pipeline</button>
        <button type="button" class="ghost" :aria-expanded="drawerOpen" @click="drawerOpen = !drawerOpen">
          <span class="lbl-full">Merchant rules</span><span class="lbl-short">Rules</span>
          <Chevron :open="drawerOpen" />
        </button>
      </div>
    </header>

    <form v-if="drawerOpen && rules" class="drawer" @submit.prevent="onSave">
      <p class="drawer-note">Hard limits are enforced by the gates and never shown to the model.</p>
      <label>Max discount %<input type="number" v-model.number="rules.hard.max_discount_pct" min="0" max="90" :disabled="rules.locked" /></label>
      <label>Min margin %<input type="number" v-model.number="rules.hard.min_margin_pct" min="0" max="90" :disabled="rules.locked" /></label>
      <label>Negotiation style<input v-model="rules.soft.negotiation_style" :disabled="rules.locked" /></label>
      <p v-if="rules.locked" class="drawer-locked">Locked for the demo. These limits apply to every run.</p>
      <div v-else class="drawer-actions">
        <button class="primary" type="submit">Save rules</button>
        <span class="status">{{ saveState }}</span>
      </div>
    </form>

    <HistoryPanel :runs="runs" :run-id="runId" :running="running" @replay="emit('replay', $event)" @delete="emit('delete', $event)" @clear="emit('clear')" />

    <div class="thread-wrap scroll">
      <div v-if="!bubbles.length && !running" class="thread-empty">
        <p v-if="showcase"><strong>Pick an example below.</strong> Each one replays a real recorded run: a buyer's AI agent asking the store for something, and MACS answering.</p>
        <p v-else><strong>You play the buyer's AI agent.</strong> Type what it would ask the store, pick an identity, and run.</p>
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

    <Composer :running="running" :error="error" :showcase="showcase" @run="emit('run', $event)" />
  </aside>
</template>
