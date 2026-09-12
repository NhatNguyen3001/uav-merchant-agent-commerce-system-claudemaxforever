<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import Conversation from './components/Conversation.vue'
import Pipeline from './components/Pipeline.vue'
import { deleteRun, clearHistory, fetchRuns, useRun } from './composables/useRun.js'

const { events, runId, running, error, start } = useRun()
const runs = ref([])
const draft = ref(null) // the typed query shown in the chat before the backend echoes it

const PIPELINE_KEY = 'macs.pipeline.visible'
const pipelineVisible = ref(false)
try {
  pipelineVisible.value = localStorage.getItem(PIPELINE_KEY) === '1'
} catch (_) {}
watch(pipelineVisible, (v) => {
  try {
    localStorage.setItem(PIPELINE_KEY, v ? '1' : '0')
  } catch (_) {}
})

async function refreshRuns() {
  runs.value = await fetchRuns()
}

async function run(body) {
  draft.value = body.query ? { agent_id: body.agent_id, text: body.query } : null
  await start(body)
  setTimeout(refreshRuns, 1200)
}

// The run document is finalised before the stream closes, so refreshing when `running` drops
// picks up the final status (placed, blocked, failed) without a page reload.
watch(running, (now, before) => {
  if (before && !now) refreshRuns()
})

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
  <div class="layout" :class="{ 'pipeline-hidden': !pipelineVisible }">
    <Conversation
      :messages="messages"
      :draft="draft"
      :runs="runs"
      :run-id="runId"
      :running="running"
      :error="error"
      :pipeline-visible="pipelineVisible"
      @run="run"
      @replay="run({ scenario: $event })"
      @delete="onDelete"
      @clear="onClear"
      @show-pipeline="pipelineVisible = true"
    />
    <Pipeline v-if="pipelineVisible" :events="pipelineEvents" :stages="stageEvents" :running="running" @hide="pipelineVisible = false" />
  </div>
</template>
