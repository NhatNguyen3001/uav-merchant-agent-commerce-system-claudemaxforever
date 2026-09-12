<script setup>
import { computed, onMounted, ref } from 'vue'
import Conversation from './components/Conversation.vue'
import Pipeline from './components/Pipeline.vue'
import { deleteRun, clearHistory, fetchRuns, useRun } from './composables/useRun.js'

const { events, runId, running, error, start } = useRun()
const runs = ref([])
const draft = ref(null) // the typed query shown in the chat before the backend echoes it

async function refreshRuns() {
  runs.value = await fetchRuns()
}

async function run(body) {
  draft.value = body.query ? { agent_id: body.agent_id, text: body.query } : null
  await start(body)
  setTimeout(refreshRuns, 1200)
}

async function onDelete(id) {
  await deleteRun(id)
  await refreshRuns()
}

async function onClear() {
  await clearHistory()
  await refreshRuns()
}

onMounted(refreshRuns)

const stageEvents = computed(() => events.value.filter((e) => e.type === 'stage'))
const messages = computed(() => events.value.filter((e) => e.type === 'message'))
const pipelineEvents = computed(() => events.value.filter((e) => e.lane === 'a2a' && e.type !== 'message'))
</script>

<template>
  <div class="layout">
    <Conversation
      :messages="messages"
      :draft="draft"
      :runs="runs"
      :run-id="runId"
      :running="running"
      :error="error"
      @run="run"
      @replay="run({ scenario: $event })"
      @delete="onDelete"
      @clear="onClear"
    />
    <Pipeline :events="pipelineEvents" :stages="stageEvents" :running="running" />
  </div>
</template>
