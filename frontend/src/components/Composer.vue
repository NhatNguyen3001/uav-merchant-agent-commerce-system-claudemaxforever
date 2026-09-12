<script setup>
import { onMounted, ref } from 'vue'
import { fetchAgents } from '../composables/useRun.js'

const props = defineProps({ running: Boolean, error: String })
const emit = defineEmits(['run'])

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

function useExample(text) {
  query.value = text
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
  <section class="composer">
    <textarea
      ref="box"
      v-model="query"
      rows="2"
      class="query"
      placeholder="What does the incoming agent say? Enter to run"
      @keydown="onKeydown"
    ></textarea>
    <div class="composer-row">
      <select v-model="agentId" class="agent" aria-label="Agent identity">
        <option v-for="a in agents" :key="a.agent_id" :value="a.agent_id">{{ a.agent_id }} ({{ a.label }})</option>
      </select>
      <button class="primary" :disabled="running || !query.trim()" @click="submit">
        {{ running ? 'Running' : 'Run' }}
      </button>
    </div>
    <div class="examples">
      <span class="examples-label">Try</span>
      <button v-for="ex in EXAMPLES" :key="ex.label" class="chip" type="button" @click="useExample(ex.text)">{{ ex.label }}</button>
    </div>
    <p v-if="error" class="error">{{ error }}</p>
  </section>
</template>
