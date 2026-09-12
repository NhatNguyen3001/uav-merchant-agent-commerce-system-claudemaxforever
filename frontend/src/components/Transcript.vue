<script setup>
import { computed, nextTick, ref, watch } from 'vue'

const props = defineProps({
  events: { type: Array, required: true },
  stages: { type: Array, required: true },
  running: Boolean,
})

const list = ref(null)

// While the latest stage is still running, show a placeholder at the bottom for what is being worked on.
const pending = computed(() => {
  if (!props.running) return null
  const lastStage = props.stages[props.stages.length - 1]
  if (!lastStage || lastStage.payload.status !== 'running') return null
  return {
    protocol_adapter: 'Reading the incoming message',
    inbound_gate: 'Checking credentials and mandate',
    intent_decoder: 'Decoding intent',
    proposal_engine: 'Matching the catalogue and composing a bundle',
    outbound_gate: 'Checking the proposal against merchant rules',
    execution_gate: 'Checking the mandate',
    retailer_systems: 'Placing the order',
  }[lastStage.payload.stage]
})

watch(
  () => [props.events.length, pending.value],
  async () => {
    if (!props.running) return
    await nextTick()
    list.value?.lastElementChild?.scrollIntoView({ block: 'end', behavior: 'smooth' })
  },
)

const gateTitle = (p) => `${p.gate.charAt(0).toUpperCase() + p.gate.slice(1)} gate ${p.verdict === 'pass' ? 'passed' : p.verdict}`
const money = (n) => Number(n).toLocaleString(undefined, { maximumFractionDigits: 2 })
</script>

<template>
  <section class="transcript">
    <div v-if="!events.length && !running" class="transcript-empty">
      <img src="/logo-full.png" alt="MACS" />
      <p>Gates, decoded intent, tool calls, proposals, and the order appear here as each stage finishes.</p>
      <p>Every price comes from a tool result, and every gate verdict is deterministic.</p>
    </div>

    <ol ref="list" class="blocks">
      <li v-for="e in events" :key="e.id" :class="['block', e.type, e.type === 'gate' ? e.payload.verdict : '']">
        <template v-if="e.type === 'intent'">
          <p class="who">Decoded intent<span class="tag">{{ e.payload.constraint_count }} constraints</span></p>
          <dl class="intent">
            <dt>Goal</dt><dd>{{ e.payload.goal }}</dd>
            <dt>Skill</dt><dd>{{ e.payload.skill_level }}</dd>
            <dt>Environment</dt><dd>{{ e.payload.environment.join(', ') }}</dd>
            <dt>Values</dt><dd>{{ e.payload.values.join(', ') }}</dd>
            <dt>Hard limits</dt><dd>budget {{ money(e.payload.hard_constraints.budget_max) }}, within {{ e.payload.hard_constraints.deliver_by_days }} days</dd>
            <dt>Prefers</dt><dd>{{ e.payload.soft_preferences.join(', ') }}</dd>
          </dl>
        </template>

        <template v-else-if="e.type === 'tool'">
          <p class="who">Tool call <code>{{ e.payload.name }}</code><span class="tag">{{ e.payload.latency_ms }} ms</span></p>
          <p class="text quiet">{{ e.payload.result_summary }}</p>
        </template>

        <template v-else-if="e.type === 'gate'">
          <p class="who">{{ gateTitle(e.payload) }}</p>
          <p class="text">{{ e.payload.reason }}</p>
          <p v-if="e.payload.before" class="diff">
            <span class="before">{{ money(e.payload.before.bundle_price) }} at {{ e.payload.before.discount_pct }}% off</span>
            <span class="arrow" aria-hidden="true"></span>
            <span class="after">{{ money(e.payload.after.bundle_price) }} at {{ e.payload.after.discount_pct }}% off</span>
          </p>
        </template>

        <template v-else-if="e.type === 'proposal'">
          <p class="who">Proposal<span class="tag">{{ money(e.payload.bundle_price) }}, {{ e.payload.discount_pct }}% off list, covers {{ e.payload.intent_coverage }}</span></p>
          <ul class="items">
            <li v-for="it in e.payload.items" :key="it.sku">
              <div class="item-head"><span class="item-name">{{ it.name }}</span><span class="item-price num">{{ money(it.price) }}</span></div>
              <p class="text">{{ it.rationale }}</p>
              <p class="quiet">Satisfies {{ it.satisfies.join(', ') }}</p>
            </li>
          </ul>
          <p v-if="e.payload.alternative" class="alt">
            Alternative: {{ e.payload.alternative.name }} brings the bundle to {{ money(e.payload.alternative.bundle_price) }}. {{ e.payload.alternative.tradeoff }}
          </p>
        </template>

        <template v-else-if="e.type === 'order'">
          <p class="who">{{ e.payload.status === 'placed' ? 'Order placed' : 'Order rejected' }}</p>
          <p class="text">{{ e.payload.order_id ? e.payload.order_id + ', ' : '' }}{{ e.payload.skus.join(', ') }}, total {{ money(e.payload.total) }}</p>
        </template>
      </li>

      <li v-if="pending" class="block pending" aria-live="polite">
        <span class="shimmer"></span>{{ pending }}
      </li>
    </ol>
  </section>
</template>
