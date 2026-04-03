<script setup lang="ts">
defineProps<{
  lines?: number;
  className?: string;
}>();
</script>

<template>
  <div class="animate-pulse space-y-2" :class="className">
    <div v-for="index in lines ?? 3" :key="index" class="h-3 rounded-full bg-surface-3" :style="{ width: `${100 - index * 12}%` }" />
  </div>
</template>
