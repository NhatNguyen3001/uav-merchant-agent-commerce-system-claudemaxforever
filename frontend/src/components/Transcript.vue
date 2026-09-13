<script setup>
import { computed, nextTick, reactive, ref, watch } from 'vue'
import Chevron from './Chevron.vue'
import { coverage, days, money, pct } from '../format.js'

const props = defineProps({
  events: { type: Array, required: true },
  stages: { type: Array, required: true },
  running: Boolean,
})

const list = ref(null)
const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1)

// What each requirement key means to a person.
const FACET = { goal: 'goal', skill_level: 'skill level', environment: 'environment', values: 'values',
                hard_constraints: 'budget and deadline', soft_preferences: 'preferences' }
const facets = (keys) => keys.map((k) => FACET[k] || k.replace(/_/g, ' ')).join(', ')

// What each tool does, for the row heading; the tool name stays beside it.
const TOOL = { semantic_search: 'Semantic search', search_products: 'Hard filters', get_product: 'Product lookup',
               get_price: 'Price check', get_shipping: 'Shipping check', create_order: 'Order placement' }
const CATALOGUE = new Set(['semantic_search', 'search_products', 'get_product', 'get_price'])

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

// Intent and proposal open by default (they are what the demo is judged on); gates and lookups start folded.
const OPEN_BY_DEFAULT = { intent: true, proposal: true, decision: false, order: true, gate: false, tools: false }
const openState = reactive({})
const isOpen = (row) => (row.id in openState ? openState[row.id] : OPEN_BY_DEFAULT[row.kind])
const toggle = (row) => (openState[row.id] = !isOpen(row))

const GATE_TITLE = {
  inbound: { pass: 'Inbound gate: buyer verified', blocked: 'Inbound gate: refused' },
  outbound: { pass: 'Outbound gate: within merchant rules', corrected: 'Outbound gate: corrected', blocked: 'Outbound gate: blocked' },
  execution: { pass: 'Execution gate: mandate allows it', blocked: 'Execution gate: blocked' },
}

function title(row) {
  const p = row.event?.payload
  switch (row.kind) {
    case 'gate': return GATE_TITLE[p.gate]?.[p.verdict] || `${cap(p.gate)} gate ${p.verdict}`
    case 'intent': return p.constraint_count ? `Decoded intent: ${p.constraint_count} requirements` : 'Decoded intent'
    case 'tools': {
      const names = row.items.map((t) => t.payload.name)
      if (names.every((n) => CATALOGUE.has(n))) return `Catalogue lookups (${names.length})`
      if (names.every((n) => n === 'get_shipping')) return `Shipping checks (${names.length})`
      if (names.every((n) => n === 'create_order')) return 'Order sent to the retailer'
      return `Tool calls (${names.length})`
    }
    case 'proposal': return 'Proposal'
    case 'decision': return p.action === 'accept' ? `Buyer's agent agrees (round ${p.round})` : `Buyer's agent asks for a lower price (round ${p.round})`
    case 'order': return p.status === 'placed' ? 'Order placed' : 'No order'
    default: return row.kind
  }
}

// Only the proposal row carries a summary next to its title; the others read as plain headings.
function meta(row) {
  const p = row.event?.payload
  if (row.kind === 'proposal') return `${money(p.bundle_price)}, ${pct(p.discount_pct)} off${p.delivery_days != null ? `, arrives in ${days(p.delivery_days)}` : ''}`
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
      <p>What happens behind the merchant's reply: the identity check, the decoded intent, the catalogue lookups, the proposal, the rule checks, and the order.</p>
      <p>Every price comes from the catalogue, and every gate decision is a fixed rule, not a model's opinion.</p>
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
              <dt>Hard limits</dt><dd>budget {{ money(row.event.payload.hard_constraints.budget_max) }}, delivered within {{ days(row.event.payload.hard_constraints.deliver_by_days) }}</dd>
              <dt>Prefers</dt><dd>{{ row.event.payload.soft_preferences.join(', ') }}</dd>
            </dl>
          </template>

          <template v-else-if="row.kind === 'tools'">
            <ul class="tools">
              <li v-for="t in row.items" :key="t.id">
                <p class="tool-name"><span>{{ TOOL[t.payload.name] || t.payload.name }}</span><code class="sku">{{ t.payload.name }}</code><span class="tag">{{ t.payload.latency_ms }} ms</span></p>
                <p class="text quiet">{{ t.payload.result_summary }}</p>
              </li>
            </ul>
          </template>

          <template v-else-if="row.kind === 'gate'">
            <p class="text">{{ row.event.payload.reason }}</p>
            <p v-if="row.event.payload.before" class="diff">
              <span class="before">{{ money(row.event.payload.before.bundle_price) }} at {{ pct(row.event.payload.before.discount_pct) }} off</span>
              <span class="arrow" aria-hidden="true"></span>
              <span class="after">{{ money(row.event.payload.after.bundle_price) }} at {{ pct(row.event.payload.after.discount_pct) }} off</span>
            </p>
          </template>

          <template v-else-if="row.kind === 'proposal'">
            <ul class="items">
              <li v-for="it in row.event.payload.items" :key="it.sku">
                <div class="item-head"><span class="item-name">{{ it.name }}<span class="sku">{{ it.sku }}</span></span><span class="item-price num">{{ money(it.price) }}</span></div>
                <p class="text">{{ it.rationale }}</p>
                <p class="quiet">Meets: {{ facets(it.satisfies) }}</p>
              </li>
            </ul>
            <p v-if="row.event.payload.alternative" class="alt">
              Alternative: {{ row.event.payload.alternative.name }} brings the bundle to {{ money(row.event.payload.alternative.bundle_price) }}. {{ row.event.payload.alternative.tradeoff }}<span v-if="row.event.payload.alternative.items?.length" class="sku">{{ row.event.payload.alternative.items.join(', ') }}</span>
            </p>
          </template>

          <template v-else-if="row.kind === 'decision'">
            <p class="text">{{ row.event.payload.message }}</p>
            <p v-if="row.event.payload.action === 'counter' && row.event.payload.counter_budget" class="quiet">Merchant proposed {{ money(row.event.payload.proposal_price) }}; the buyer's agent asks for {{ money(row.event.payload.counter_budget) }}</p>
            <p v-else class="quiet">Accepted at {{ money(row.event.payload.proposal_price) }}</p>
          </template>

          <template v-else-if="row.kind === 'order'">
            <p v-if="row.event.payload.status === 'placed'" class="text">Order {{ row.event.payload.order_id }}: {{ row.event.payload.skus.length }} items, total {{ money(row.event.payload.total) }}<template v-if="row.event.payload.ship_days != null">, ships in {{ days(row.event.payload.ship_days) }}</template>. Sent to the retailer's order system.</p>
            <p v-else class="text">Nothing was ordered. The last proposal ({{ money(row.event.payload.total) }}) stays open until it expires.</p>
            <p class="quiet"><span class="sku">{{ row.event.payload.skus.join(', ') }}</span></p>
          </template>
        </div>
      </li>

      <li v-if="pending" class="block pending" aria-live="polite">
        <span class="shimmer"></span>{{ pending }}
      </li>
    </ol>
  </section>
</template>
