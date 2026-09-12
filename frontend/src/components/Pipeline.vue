<script setup>
import { computed } from 'vue'
import ProgressBar from './ProgressBar.vue'
import Transcript from './Transcript.vue'

const props = defineProps({
  events: { type: Array, required: true },
  stages: { type: Array, required: true },
  running: Boolean,
})
const emit = defineEmits(['hide'])

const last = (type) => [...props.events].reverse().find((e) => e.type === type)
const finished = computed(() => {
  if (props.running || !props.stages.length) return false
  const s = props.stages[props.stages.length - 1].payload
  return s.status === 'passed' || s.status === 'blocked'
})
const proposal = computed(() => last('proposal')?.payload)
const order = computed(() => last('order')?.payload)
const blockedStage = computed(() => [...props.stages].reverse().find((e) => e.payload.status === 'blocked')?.payload)
const money = (n) => Number(n).toLocaleString(undefined, { maximumFractionDigits: 2 })
</script>

<template>
  <main class="stage">
    <div class="stage-top">
      <ProgressBar :stages="stages" :running="running" />
      <button type="button" class="ghost hide-pipeline" @click="emit('hide')">Hide pipeline</button>
    </div>
    <div v-if="finished" class="outcome" :class="order?.status === 'placed' ? 'placed' : 'blocked'">
      <template v-if="order?.status === 'placed'">
        <span class="outcome-title">Order placed</span>
        <span>{{ proposal.items.length }} items, {{ money(proposal.bundle_price) }} total, {{ (100 - proposal.discount_pct).toFixed(0) }}% of list retained, intent coverage {{ proposal.intent_coverage }}<template v-if="proposal.delivery_days != null">, arrives in {{ proposal.delivery_days }} day{{ proposal.delivery_days === 1 ? '' : 's' }}</template></span>
      </template>
      <template v-else>
        <span class="outcome-title">No order</span>
        <span>{{ blockedStage ? blockedStage.note : 'The run ended without an order.' }}</span>
      </template>
    </div>
    <Transcript :events="events" :stages="stages" :running="running" />
  </main>
</template>
