<script setup>
defineProps({ events: { type: Array, required: true } })
</script>

<template>
  <section>
    <h2>Agent-to-agent transcript <span class="muted">buyer agent is external traffic</span></h2>
    <div v-for="e in events" :key="e.id" :class="['block', e.type]">
      <template v-if="e.type === 'message'">
        <div class="who">{{ e.payload.from === 'buyer_agent' ? 'Buyer agent (external)' : 'Merchant agent' }}</div>
        <p>{{ e.payload.text }}</p>
      </template>

      <template v-else-if="e.type === 'intent'">
        <div class="who">Decoded intent · {{ e.payload.constraint_count }} constraints</div>
        <dl class="intent">
          <dt>Goal</dt><dd>{{ e.payload.goal }}</dd>
          <dt>Skill</dt><dd>{{ e.payload.skill_level }}</dd>
          <dt>Environment</dt><dd>{{ e.payload.environment.join(', ') }}</dd>
          <dt>Values</dt><dd>{{ e.payload.values.join(', ') }}</dd>
          <dt>Hard limits</dt><dd>budget {{ e.payload.hard_constraints.budget_max }}, {{ e.payload.hard_constraints.deliver_by_days }} days</dd>
          <dt>Soft</dt><dd>{{ e.payload.soft_preferences.join(', ') }}</dd>
        </dl>
      </template>

      <template v-else-if="e.type === 'tool'">
        <div class="who">Tool · {{ e.payload.name }} · {{ e.payload.latency_ms }} ms</div>
        <p class="mono">{{ e.payload.result_summary }}</p>
      </template>

      <template v-else-if="e.type === 'gate'">
        <div class="who">{{ e.payload.gate }} gate · <span :class="e.payload.verdict">{{ e.payload.verdict }}</span></div>
        <p>{{ e.payload.reason }}</p>
        <p class="mono" v-if="e.payload.before">before {{ e.payload.before }} → after {{ e.payload.after }}</p>
      </template>

      <template v-else-if="e.type === 'proposal'">
        <div class="who">Proposal · {{ e.payload.bundle_price }} ({{ e.payload.discount_pct }}% off) · coverage {{ e.payload.intent_coverage }}</div>
        <ul class="items">
          <li v-for="it in e.payload.items" :key="it.sku">
            <strong>{{ it.name }}</strong> <span class="muted">{{ it.sku }} · {{ it.price }}</span>
            <div>{{ it.rationale }}</div>
            <div class="muted">satisfies: {{ it.satisfies.join(', ') }}</div>
          </li>
        </ul>
        <p v-if="e.payload.alternative" class="alt">
          Alternative: {{ e.payload.alternative.name }} → bundle {{ e.payload.alternative.bundle_price }}. {{ e.payload.alternative.tradeoff }}
        </p>
      </template>

      <template v-else-if="e.type === 'order'">
        <div class="who">Order · <span :class="e.payload.status">{{ e.payload.status }}</span></div>
        <p>{{ e.payload.order_id || 'no order' }} · {{ e.payload.skus.join(', ') }} · total {{ e.payload.total }}</p>
      </template>
    </div>
  </section>
</template>
