<script setup>
import { computed, onMounted, ref } from 'vue'
import { fetchRules, saveRules } from '../composables/useRun.js'

const props = defineProps({ events: Array, runs: Array, runId: String, running: Boolean })
const emit = defineEmits(['replay'])

const rules = ref(null)
const drawerOpen = ref(false)
const saveState = ref('')

onMounted(async () => {
  rules.value = await fetchRules()
})

async function onSave() {
  saveState.value = 'Saving'
  await saveRules(rules.value)
  saveState.value = 'Saved'
  setTimeout(() => (saveState.value = ''), 1500)
}

const last = (type) => [...props.events].reverse().find((e) => e.type === type)
const proposal = computed(() => last('proposal')?.payload)
const order = computed(() => last('order')?.payload)
const gates = computed(() => props.events.filter((e) => e.type === 'gate').map((e) => e.payload))
const blockedStage = computed(() => [...props.events].reverse().find((e) => e.type === 'stage' && e.payload.status === 'blocked')?.payload)

const margin = computed(() => (proposal.value ? `${(100 - proposal.value.discount_pct).toFixed(0)}% of list` : ''))

function when(r) {
  const d = new Date(r.started_at)
  return isNaN(d) ? '' : d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function title(r) {
  if (r.is_golden) return r.scenario === 'happy_path' ? 'Golden: podcast starter' : 'Golden: unregistered agent'
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
  <aside class="rail">
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

    <section class="result">
      <h2>Result</h2>
      <p v-if="!proposal && !gates.length && !running" class="empty">Run a query to see the outcome here.</p>
      <p v-else-if="!proposal && running" class="empty">Working</p>
      <dl v-if="proposal" class="facts">
        <dt>Bundle</dt><dd>{{ proposal.items.map((i) => i.sku).join(', ') }}</dd>
        <dt>Price</dt><dd class="num">{{ proposal.bundle_price }}</dd>
        <dt>Intent coverage</dt><dd>{{ proposal.intent_coverage }}</dd>
        <dt>Margin retained</dt><dd>{{ margin }}</dd>
      </dl>
      <ul class="verdicts">
        <li v-for="(g, i) in gates" :key="i" :class="g.verdict">
          <span class="mark"></span>{{ g.gate }} gate {{ g.verdict }}
        </li>
        <li v-if="order" :class="order.status"><span class="mark"></span>order {{ order.status }}<span v-if="order.order_id" class="muted"> {{ order.order_id }}</span></li>
        <li v-else-if="blockedStage" class="blocked"><span class="mark"></span>no order</li>
      </ul>
    </section>

    <section class="history">
      <h2>History</h2>
      <p v-if="!runs.length" class="empty">No runs yet.</p>
      <ul>
        <li v-for="r in runs" :key="r.run_id">
          <button type="button" class="run" :class="{ current: r.run_id === runId }" :disabled="running" @click="emit('replay', r.run_id)">
            <span class="run-title">{{ title(r) }}</span>
            <span class="run-meta"><span>{{ when(r) }}</span><span :class="outcome(r).split(' ')[0]">{{ outcome(r) }}</span></span>
          </button>
        </li>
      </ul>
    </section>
  </aside>
</template>
