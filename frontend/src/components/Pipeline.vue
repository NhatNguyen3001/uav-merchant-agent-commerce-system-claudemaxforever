<script setup>
import { computed } from 'vue'
import ProgressBar from './ProgressBar.vue'
import Transcript from './Transcript.vue'
import { coverage, days, money, pct } from '../format.js'

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
        <span>{{ proposal.items.length }} items for {{ money(proposal.bundle_price) }}<template v-if="proposal.delivery_days != null">, delivered in {{ days(proposal.delivery_days) }}</template>. {{ pct(proposal.discount_pct) }} discount, margin kept. {{ coverage(proposal.intent_coverage) }}.</span>
      </template>
      <template v-else>
        <span class="outcome-title">No order</span>
        <span>{{ blockedStage ? blockedStage.note : 'The run ended without an order.' }}</span>
      </template>
    </div>
    <Transcript :events="events" :stages="stages" :running="running" />
  </main>
</template>
