<script setup>
import { computed } from 'vue'

const props = defineProps({ stages: { type: Array, required: true } })

const ORDER = [
  ['protocol_adapter', 'Protocol adapter'],
  ['inbound_gate', 'Inbound gate'],
  ['intent_decoder', 'Intent decoder'],
  ['proposal_engine', 'Proposal engine'],
  ['outbound_gate', 'Outbound gate'],
  ['execution_gate', 'Execution gate'],
  ['retailer_systems', 'Retailer systems'],
]

const cells = computed(() =>
  ORDER.map(([key, label]) => {
    const latest = [...props.stages].reverse().find((e) => e.payload.stage === key)
    return { key, label, status: latest ? latest.payload.status : 'idle', note: latest ? latest.payload.note : '' }
  }),
)
</script>

<template>
  <ol class="pipeline">
    <li v-for="c in cells" :key="c.key" :class="['stage', c.status]">
      <div class="stage-name">{{ c.label }}</div>
      <div class="stage-status">{{ c.status }}</div>
      <div class="stage-note" :title="c.note">{{ c.note }}</div>
    </li>
  </ol>
</template>
