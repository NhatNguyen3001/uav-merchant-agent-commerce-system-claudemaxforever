<script setup>
import { computed } from 'vue'

const props = defineProps({ stages: { type: Array, required: true }, running: Boolean })

const ORDER = [
  ['protocol_adapter', 'Received'],
  ['inbound_gate', 'Inbound'],
  ['intent_decoder', 'Intent'],
  ['proposal_engine', 'Proposal'],
  ['outbound_gate', 'Outbound'],
  ['execution_gate', 'Execution'],
  ['retailer_systems', 'Order'],
]

const nodes = computed(() =>
  ORDER.map(([key, label], i) => {
    const latest = [...props.stages].reverse().find((e) => e.payload.stage === key)
    const status = latest ? latest.payload.status : 'idle'
    return { key, label, status, note: latest ? latest.payload.note : '', index: i, pct: (i / (ORDER.length - 1)) * 100 }
  }),
)

// The fill reaches the furthest stage that has started; a blocked stage ends it there.
const reach = computed(() => {
  let last = -1
  nodes.value.forEach((n) => {
    if (n.status !== 'idle') last = n.index
  })
  return last
})
const current = computed(() => nodes.value[reach.value] || null)
const fillPct = computed(() => (reach.value < 0 ? 0 : nodes.value[reach.value].pct))
const state = computed(() => (current.value ? current.value.status : 'idle'))

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
  if (n.key === 'retailer_systems') return ''
  return n.note
})
</script>

<template>
  <section class="progress" :class="state">
    <div class="bar">
      <div class="bar-track">
        <div class="bar-fill" :style="{ width: fillPct + '%' }"></div>
        <span v-for="n in nodes" :key="n.key" class="tick" :class="[n.status, { reached: n.index <= reach }]" :style="{ left: n.pct + '%' }"></span>
        <span v-if="reach >= 0" class="knob" :style="{ left: fillPct + '%' }"></span>
      </div>
      <ol class="bar-labels">
        <li v-for="n in nodes" :key="n.key" :class="[n.status, { current: n.index === reach }]" :style="{ left: n.pct + '%' }" :title="n.note">{{ n.label }}</li>
      </ol>
    </div>
    <p class="caption" :class="state">{{ caption }}</p>
  </section>
</template>
