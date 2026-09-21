<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import Conversation from './components/Conversation.vue'
import MobileTabs from './components/MobileTabs.vue'
import Pipeline from './components/Pipeline.vue'
import { deleteRun, clearHistory, fetchHealth, fetchRuns, useRun } from './composables/useRun.js'

const { events, runId, running, error, start } = useRun()
const runs = ref([])
const showcase = ref(false) // recorded examples only: typed queries are switched off on the hosted demo
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
onMounted(async () => {
  showcase.value = !!(await fetchHealth().catch(() => ({}))).replay
})

// Phones and small tablets show one panel at a time behind a bottom tab bar.
const mql = typeof window !== 'undefined' && window.matchMedia ? window.matchMedia('(max-width: 960px)') : null
const isMobile = ref(mql ? mql.matches : false)
const mobileTab = ref('chat')
const onMedia = (e) => (isMobile.value = e.matches)
onMounted(() => mql?.addEventListener('change', onMedia))
onBeforeUnmount(() => mql?.removeEventListener('change', onMedia))

const showConversation = computed(() => !isMobile.value || mobileTab.value === 'chat')
const showPipeline = computed(() => (isMobile.value ? mobileTab.value === 'pipeline' : pipelineVisible.value))

const stageEvents = computed(() => events.value.filter((e) => e.type === 'stage'))
const messages = computed(() => events.value.filter((e) => e.type === 'message'))
const pipelineEvents = computed(() => events.value.filter((e) => e.lane === 'a2a' && e.type !== 'message'))
const outcome = computed(() => {
  if (running.value || !stageEvents.value.length) return null
  const last = stageEvents.value[stageEvents.value.length - 1].payload
  if (last.status === 'blocked') return 'blocked'
  return last.status === 'passed' && last.stage === 'retailer_systems' ? 'placed' : null
})
</script>

<template>
  <div class="layout" :class="{ 'pipeline-hidden': !showPipeline, mobile: isMobile }">
    <Conversation
      v-if="showConversation"
      :messages="messages"
      :draft="draft"
      :runs="runs"
      :run-id="runId"
      :running="running"
      :error="error"
      :pipeline-visible="pipelineVisible"
      :mobile="isMobile"
      :showcase="showcase"
      @run="run"
      @replay="run({ scenario: $event })"
      @delete="onDelete"
      @clear="onClear"
      @show-pipeline="pipelineVisible = true"
    />
    <Pipeline v-if="showPipeline" :events="pipelineEvents" :stages="stageEvents" :running="running" :mobile="isMobile" @hide="pipelineVisible = false" />
    <MobileTabs v-if="isMobile" :tab="mobileTab" :running="running" :outcome="outcome" @select="mobileTab = $event" />
  </div>
</template>
