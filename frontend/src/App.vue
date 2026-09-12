<script setup>
import { computed } from 'vue'
import PipelineStrip from './components/PipelineStrip.vue'
import MerchantConsole from './components/MerchantConsole.vue'
import Transcript from './components/Transcript.vue'
import { useRun } from './composables/useRun.js'

const { events, runId, running, start } = useRun()
const stageEvents = computed(() => events.value.filter((e) => e.type === 'stage'))
const a2aEvents = computed(() => events.value.filter((e) => e.lane === 'a2a'))
</script>

<template>
  <div class="layout">
    <header class="strip">
      <PipelineStrip :stages="stageEvents" />
    </header>
    <aside class="console">
      <MerchantConsole :events="events" :run-id="runId" :running="running" @start="start" />
    </aside>
    <main class="transcript">
      <Transcript :events="a2aEvents" />
    </main>
  </div>
</template>
