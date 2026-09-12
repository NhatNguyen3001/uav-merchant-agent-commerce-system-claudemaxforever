<script setup>
import { computed, onMounted, ref } from 'vue'
import { fetchRules, fetchRuns, saveRules } from '../composables/useRun.js'

const props = defineProps({ events: Array, runId: String, running: Boolean })
const emit = defineEmits(['start'])

const rules = ref(null)
const runs = ref([])
const scenario = ref('happy_path')
const saveState = ref('')

onMounted(async () => {
  rules.value = await fetchRules()
  runs.value = await fetchRuns()
})

async function onSave() {
  saveState.value = 'saving'
  await saveRules(rules.value)
  saveState.value = 'saved'
}

async function onStart() {
  emit('start', scenario.value)
  setTimeout(async () => (runs.value = await fetchRuns()), 1500)
}

const last = (type, pred = () => true) => [...props.events].reverse().find((e) => e.type === type && pred(e))
const proposal = computed(() => last('proposal')?.payload)
const order = computed(() => last('order')?.payload)
const gates = computed(() => props.events.filter((e) => e.type === 'gate').map((e) => e.payload))
const marginRetained = computed(() => {
  if (!proposal.value) return null
  return `${(100 - proposal.value.discount_pct).toFixed(1)}% of list`
})
</script>

<template>
  <section>
    <h2>Rules in effect</h2>
    <form v-if="rules" class="rules" @submit.prevent="onSave">
      <label>Max discount %<input type="number" v-model.number="rules.hard.max_discount_pct" /></label>
      <label>Min margin %<input type="number" v-model.number="rules.hard.min_margin_pct" /></label>
      <label>Negotiation style<input v-model="rules.soft.negotiation_style" /></label>
      <button type="submit">Save rules</button>
      <span class="muted">{{ saveState }}</span>
    </form>

    <h2>Simulate incoming agent</h2>
    <div class="picker">
      <select v-model="scenario">
        <option value="happy_path">Registered agent, complex podcast query</option>
        <option value="rejected_agent">Unregistered agent (buyer-999)</option>
        <option v-for="r in runs" :key="r.run_id" :value="r.run_id">
          Replay {{ r.is_golden ? 'golden' : '' }} {{ r.scenario }} {{ r.started_at }}
        </option>
      </select>
      <button :disabled="running" @click="onStart">{{ running ? 'Running…' : 'Run' }}</button>
    </div>
    <p class="muted" v-if="runId">Run {{ runId }}</p>

    <h2>Result</h2>
    <div class="card">
      <div v-if="proposal">
        <div class="row"><span>Bundle</span><strong>{{ proposal.items.map((i) => i.sku).join(', ') }}</strong></div>
        <div class="row"><span>Bundle price</span><strong>{{ proposal.bundle_price }}</strong></div>
        <div class="row"><span>Intent coverage</span><strong>{{ proposal.intent_coverage }}</strong></div>
        <div class="row"><span>Margin retained</span><strong>{{ marginRetained }}</strong></div>
      </div>
      <div class="row" v-for="(g, i) in gates" :key="i">
        <span>{{ g.gate }} gate</span><strong :class="g.verdict">{{ g.verdict }}</strong>
      </div>
      <div class="row" v-if="order"><span>Order</span><strong :class="order.status">{{ order.status }} {{ order.order_id }}</strong></div>
      <p class="muted" v-if="!proposal && !gates.length">No run yet.</p>
    </div>
  </section>
</template>
