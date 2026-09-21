<script setup>
import { onMounted, ref } from 'vue'
import { fetchAgents } from '../composables/useRun.js'

const props = defineProps({ running: Boolean, error: String, showcase: Boolean })
const emit = defineEmits(['run'])

// Showcase mode (the hosted demo): typed queries are switched off, so these recorded runs are the only way in.
const RECORDED = [
  { scenario: 'happy_path', label: 'Podcast starter', note: 'Registered buyer, negotiates once' },
  { scenario: 'instant_buyer', label: 'Gym earbuds, no haggling', note: 'Registered buyer, accepts the first offer' },
  { scenario: 'rejected_agent', label: 'Unregistered agent', note: 'Refused at the inbound gate' },
]

const agents = ref([])
const agentId = ref('buyer-001')
const query = ref('')
const box = ref(null)

const EXAMPLES = [
  {
    label: 'Podcast starter',
    text: "I'm starting a podcast from a small apartment on a noisy street. Complete beginner. Sustainable brands only. Budget is 600 and I need everything by next weekend.",
  },
  {
    label: 'Gym earbuds',
    text: 'Wireless earbuds with noise cancelling for the gym, plus a power bank for travel, under 250, need them by Sunday.',
  },
  {
    // Same request as "Gym earbuds", sent as the buyer that accepts the first offer: one round, no counter.
    label: 'Gym earbuds, no haggling',
    text: 'Wireless earbuds with noise cancelling for the gym, plus a power bank for travel, under 250, need them by Sunday.',
    agent: 'buyer-002',
  },
  {
    label: 'Skincare routine',
    text: 'A red light therapy mask and under-eye patches for sensitive skin, cruelty-free brands only, under 300, delivered within a week.',
  },
  {
    label: 'Flight reading',
    text: 'Three uplifting Kindle novels for a long flight on Friday, under 15 in total.',
  },
  {
    label: 'Home theatre',
    text: 'Mount a 55 inch TV in a rental apartment and add a surge-protected power strip, under 120, delivered this week.',
  },
]

onMounted(async () => {
  agents.value = await fetchAgents()
})

function submit() {
  const text = query.value.trim()
  if (!text || props.running) return
  emit('run', { agent_id: agentId.value, query: text })
}

function useExample(example) {
  query.value = example.text
  if (example.agent) agentId.value = example.agent // a chip may pick the identity the example is written for
  box.value?.focus()
}

function onKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    submit()
  }
}
</script>

<template>
  <section v-if="showcase" class="composer showcase">
    <p class="examples-label">Replay a recorded run</p>
    <button
      v-for="ex in RECORDED"
      :key="ex.scenario"
      type="button"
      class="recorded"
      :disabled="running"
      @click="emit('run', { scenario: ex.scenario })"
    >
      <span class="recorded-label">{{ ex.label }}</span>
      <span class="recorded-note">{{ ex.note }}</span>
    </button>
    <p v-if="error" class="error">{{ error }}</p>
  </section>

  <section v-else class="composer">
    <textarea
      ref="box"
      v-model="query"
      rows="2"
      class="query"
      placeholder="What does the buyer's agent ask for? Enter to run"
      @keydown="onKeydown"
    ></textarea>
    <fieldset class="agents">
      <legend>Send as</legend>
      <label v-for="a in agents" :key="a.agent_id" class="agent-card" :class="{ picked: agentId === a.agent_id, refused: a.agent_id === 'buyer-999' }">
        <input type="radio" name="agent" :value="a.agent_id" v-model="agentId" />
        <span class="agent-label">{{ a.label }}</span>
        <span class="agent-id">{{ a.agent_id }}</span>
      </label>
    </fieldset>
    <button class="primary run-btn" :disabled="running || !query.trim()" @click="submit">
      {{ running ? 'Running' : 'Run' }}
    </button>
    <div class="examples">
      <span class="examples-label">Try</span>
      <button v-for="ex in EXAMPLES" :key="ex.label" class="chip" type="button" @click="useExample(ex)">{{ ex.label }}</button>
    </div>
    <p v-if="error" class="error">{{ error }}</p>
  </section>
</template>
