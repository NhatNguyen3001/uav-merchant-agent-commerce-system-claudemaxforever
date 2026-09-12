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
  { label: 'Field interviews', text: 'Two lavalier mics and a small recorder for street interviews, under 300, shipping within 3 days.' },
  { label: 'Upgrade the room', text: 'Already have a USB mic. Want to tame echo in a 3 by 3 metre room and add closed back headphones, budget 400.' },
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
    <div class="composer-row">
      <select v-model="agentId" class="agent" aria-label="Agent identity">
        <option v-for="a in agents" :key="a.agent_id" :value="a.agent_id">{{ a.agent_id }} ({{ a.label }})</option>
      </select>
      <textarea
        ref="box"
        v-model="query"
        rows="1"
        class="query"
        placeholder="Type what the incoming agent says, then press Enter"
        @keydown="onKeydown"
      ></textarea>
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
