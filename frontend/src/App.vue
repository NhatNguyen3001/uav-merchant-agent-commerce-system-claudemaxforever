<script setup>
import { computed, onMounted, ref } from 'vue'
import Composer from './components/Composer.vue'
import ProgressBar from './components/ProgressBar.vue'
import Sidebar from './components/Sidebar.vue'
import Transcript from './components/Transcript.vue'
import { fetchRuns, useRun } from './composables/useRun.js'

const { events, runId, running, error, start } = useRun()
const runs = ref([])

async function refreshRuns() {
  runs.value = await fetchRuns()
}

async function run(body) {
  await start(body)
  setTimeout(refreshRuns, 1200)
}

onMounted(refreshRuns)

const stageEvents = computed(() => events.value.filter((e) => e.type === 'stage'))
const a2aEvents = computed(() => events.value.filter((e) => e.lane === 'a2a'))
</script>

<template>
  <div class="layout">
    <Sidebar :events="events" :runs="runs" :run-id="runId" :running="running" @replay="run({ scenario: $event })" />
    <main class="stage">
      <Composer :running="running" :error="error" @run="run" />
      <ProgressBar :stages="stageEvents" :running="running" />
      <Transcript :events="a2aEvents" :stages="stageEvents" :running="running" />
    </main>
  </div>
</template>
