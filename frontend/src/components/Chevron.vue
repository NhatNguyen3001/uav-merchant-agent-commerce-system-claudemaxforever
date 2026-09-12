<script setup>
defineProps({ open: Boolean })
</script>

<template>
  <svg class="chevron" :class="{ open }" width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    <path d="M3.5 6l4.5 4.5L12.5 6" />
  </svg>
</template>
