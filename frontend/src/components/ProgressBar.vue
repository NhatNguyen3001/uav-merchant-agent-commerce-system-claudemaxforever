<script setup>
import { computed } from 'vue'

const props = defineProps({ stages: { type: Array, required: true }, running: Boolean })

const ORDER = [
  ['protocol_adapter', 'Received'],
  ['inbound_gate', 'Inbound gate'],
  ['intent_decoder', 'Intent'],
  ['proposal_engine', 'Proposal'],
  ['outbound_gate', 'Outbound gate'],
  ['execution_gate', 'Execution gate'],
  ['retailer_systems', 'Order'],
]

const nodes = computed(() =>
  ORDER.map(([key, label], i) => {
    const latest = [...props.stages].reverse().find((e) => e.payload.stage === key)
    const status = latest ? latest.payload.status : 'idle'
    return { key, label, status, note: latest ? latest.payload.note : '', index: i }
  }),
)

// The track fills up to the furthest stage that has started; a blocked stage ends it.
const reach = computed(() => {
  let last = -1
  nodes.value.forEach((n) => {
    if (n.status !== 'idle') last = n.index
  })
  return last
})

const current = computed(() => {
  const n = nodes.value[reach.value]
  if (!n) return null
  return n
})

const caption = computed(() => {
  const n = current.value
  if (!n) return ''
  if (n.status === 'running') {
    return { protocol_adapter: 'Reading the message', inbound_gate: 'Checking credentials and mandate',
             intent_decoder: 'Decoding intent', proposal_engine: 'Matching the catalogue and composing a bundle',
             outbound_gate: 'Checking the proposal against merchant rules', execution_gate: 'Checking the mandate',
             retailer_systems: 'Placing the order' }[n.key]
  }
  if (n.status === 'blocked') return `Stopped at ${n.label.toLowerCase()}: ${n.note}`
  if (n.key === 'retailer_systems') return n.note
  return n.note
})

const fillPct = computed(() => (reach.value < 0 ? 0 : (reach.value / (ORDER.length - 1)) * 100))
const state = computed(() => (current.value ? current.value.status : 'idle'))
</script>

<template>
  <section class="progress" :class="state">
    <div class="track">
      <div class="fill" :style="{ width: fillPct + '%' }"></div>
      <ol class="nodes">
        <li v-for="n in nodes" :key="n.key" :class="['node', n.status, { reached: n.index <= reach }]" :title="n.note">
          <span class="dot"></span>
          <span class="node-label">{{ n.label }}</span>
        </li>
      </ol>
    </div>
    <p class="caption" :class="state">
      <span v-if="state === 'running'" class="spinner" aria-hidden="true"></span>{{ caption }}
    </p>
  </section>
</template>
