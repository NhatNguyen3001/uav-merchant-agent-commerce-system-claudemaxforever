<script setup>
import { computed, nextTick, reactive, ref, watch } from 'vue'
import Chevron from './Chevron.vue'

const props = defineProps({
  events: { type: Array, required: true },
  stages: { type: Array, required: true },
  running: Boolean,
})

const list = ref(null)
const money = (n) => Number(n).toLocaleString(undefined, { maximumFractionDigits: 2 })
const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1)

// Rows: every pipeline event is a row, except consecutive tool calls, which fold into one row.
const rows = computed(() => {
  const out = []
  for (const e of props.events) {
    const prev = out[out.length - 1]
    if (e.type === 'tool' && prev && prev.kind === 'tools') {
      prev.items.push(e)
      continue
    }
    if (e.type === 'tool') out.push({ kind: 'tools', id: e.id, items: [e] })
    else out.push({ kind: e.type, id: e.id, event: e })
  }
  return out
})

// Every row starts collapsed except the order; the one-line summaries carry the verdict, coverage, and price.
const OPEN_BY_DEFAULT = { intent: false, proposal: false, decision: false, order: true, gate: false, tools: false }
const openState = reactive({})
const isOpen = (row) => (row.id in openState ? openState[row.id] : OPEN_BY_DEFAULT[row.kind])
const toggle = (row) => (openState[row.id] = !isOpen(row))

function title(row) {
  const p = row.event?.payload
  switch (row.kind) {
    case 'gate': return `${cap(p.gate)} gate ${p.verdict === 'pass' ? 'passed' : p.verdict}`
    case 'intent': return 'Decoded intent'
    case 'tools': return `Tool calls (${row.items.length})`
    case 'proposal': return 'Proposal'
    case 'decision': return p.action === 'accept' ? `Buyer agrees (round ${p.round})` : `Buyer counters (round ${p.round})`
    case 'order': return p.status === 'placed' ? 'Order placed' : 'Order rejected'
    default: return row.kind
  }
}

// Only the proposal row carries a summary next to its title; the others read as plain headings.
function meta(row) {
  const p = row.event?.payload
  if (row.kind === 'proposal') return `${money(p.bundle_price)}, ${p.discount_pct}% off${p.delivery_days != null ? `, arrives in ${p.delivery_days} day${p.delivery_days === 1 ? '' : 's'}` : ''}`
  return ''
}

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
</script>

<template>
  <section class="transcript scroll">
    <div v-if="!events.length && !running" class="transcript-empty">
      <img src="/logo-full.png" alt="MACS" />
      <p>Gates, decoded intent, tool calls, proposals, and the order appear here as each stage finishes.</p>
      <p>Every price comes from a tool result, and every gate verdict is deterministic.</p>
    </div>

    <ol ref="list" class="blocks">
      <li v-for="row in rows" :key="row.id" :class="['block', row.kind, row.kind === 'gate' ? row.event.payload.verdict : '', row.kind === 'decision' ? row.event.payload.action : '', { open: isOpen(row) }]">
        <button type="button" class="row-head" :aria-expanded="isOpen(row)" @click="toggle(row)">
          <span class="who">{{ title(row) }}</span>
          <span class="tag">{{ meta(row) }}</span>
          <Chevron :open="isOpen(row)" />
        </button>

        <div v-if="isOpen(row)" class="row-body">
          <template v-if="row.kind === 'intent'">
            <dl class="facts">
              <dt>Goal</dt><dd>{{ row.event.payload.goal }}</dd>
              <dt>Skill</dt><dd>{{ row.event.payload.skill_level }}</dd>
              <dt>Environment</dt><dd>{{ row.event.payload.environment.join(', ') }}</dd>
              <dt>Values</dt><dd>{{ row.event.payload.values.join(', ') }}</dd>
              <dt>Hard limits</dt><dd>budget {{ money(row.event.payload.hard_constraints.budget_max) }}, within {{ row.event.payload.hard_constraints.deliver_by_days }} days</dd>
              <dt>Prefers</dt><dd>{{ row.event.payload.soft_preferences.join(', ') }}</dd>
            </dl>
          </template>

          <template v-else-if="row.kind === 'tools'">
            <ul class="tools">
              <li v-for="t in row.items" :key="t.id">
                <p class="tool-name"><code>{{ t.payload.name }}</code><span class="tag">{{ t.payload.latency_ms }} ms</span></p>
                <p class="text quiet">{{ t.payload.result_summary }}</p>
              </li>
            </ul>
          </template>

          <template v-else-if="row.kind === 'gate'">
            <p class="text">{{ row.event.payload.reason }}</p>
            <p v-if="row.event.payload.before" class="diff">
              <span class="before">{{ money(row.event.payload.before.bundle_price) }} at {{ row.event.payload.before.discount_pct }}% off</span>
              <span class="arrow" aria-hidden="true"></span>
              <span class="after">{{ money(row.event.payload.after.bundle_price) }} at {{ row.event.payload.after.discount_pct }}% off</span>
            </p>
          </template>

          <template v-else-if="row.kind === 'proposal'">
            <ul class="items">
              <li v-for="it in row.event.payload.items" :key="it.sku">
                <div class="item-head"><span class="item-name">{{ it.name }}<span class="sku">{{ it.sku }}</span></span><span class="item-price num">{{ money(it.price) }}</span></div>
                <p class="text">{{ it.rationale }}</p>
                <p class="quiet">Satisfies {{ it.satisfies.join(', ') }}</p>
              </li>
            </ul>
            <p v-if="row.event.payload.alternative" class="alt">
              Alternative: {{ row.event.payload.alternative.name }} brings the bundle to {{ money(row.event.payload.alternative.bundle_price) }}. {{ row.event.payload.alternative.tradeoff }}<span v-if="row.event.payload.alternative.items?.length" class="sku">{{ row.event.payload.alternative.items.join(', ') }}</span>
            </p>
          </template>

          <template v-else-if="row.kind === 'decision'">
            <p class="text">{{ row.event.payload.message }}</p>
            <p v-if="row.event.payload.action === 'counter' && row.event.payload.counter_budget" class="quiet">Proposed {{ money(row.event.payload.proposal_price) }}, buyer asks for {{ money(row.event.payload.counter_budget) }}</p>
            <p v-else class="quiet">Accepted at {{ money(row.event.payload.proposal_price) }}</p>
          </template>

          <template v-else-if="row.kind === 'order'">
            <p class="text">{{ row.event.payload.order_id ? row.event.payload.order_id + ', ' : '' }}{{ row.event.payload.skus.join(', ') }}, total {{ money(row.event.payload.total) }}</p>
          </template>
        </div>
      </li>

      <li v-if="pending" class="block pending" aria-live="polite">
        <span class="shimmer"></span>{{ pending }}
      </li>
    </ol>
  </section>
</template>
