<script setup>
// Bottom tab bar for phones: one panel at a time. The Pipeline tab carries a dot while a run
// is in progress and takes the outcome colour when it ends, so a reader on Chat knows to look.
defineProps({
  tab: { type: String, required: true }, // 'chat' | 'pipeline'
  running: Boolean,
  outcome: String, // 'placed' | 'blocked' | null
})
const emit = defineEmits(['select'])
</script>

<template>
  <nav class="tabs" aria-label="Panels">
    <button type="button" :class="{ active: tab === 'chat' }" :aria-pressed="tab === 'chat'" @click="emit('select', 'chat')">Chat</button>
    <button type="button" :class="{ active: tab === 'pipeline' }" :aria-pressed="tab === 'pipeline'" @click="emit('select', 'pipeline')">
      Pipeline
      <span v-if="running || outcome" class="tab-dot" :class="running ? 'running' : outcome" aria-hidden="true"></span>
    </button>
  </nav>
</template>
