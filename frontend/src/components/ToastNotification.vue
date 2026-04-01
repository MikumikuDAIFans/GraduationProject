<script setup lang="ts">
import { watch } from "vue";
import type { ToastItem } from "@/stores/workspace";

const props = defineProps<{
  items: ToastItem[];
}>();

const emit = defineEmits<{
  dismiss: [id: string];
}>();

const scheduled = new Set<string>();

watch(
  () => props.items.map((item) => item.id),
  (ids) => {
    for (const item of props.items) {
      if (scheduled.has(item.id)) {
        continue;
      }
      scheduled.add(item.id);
      window.setTimeout(() => {
        scheduled.delete(item.id);
        emit("dismiss", item.id);
      }, 5000);
    }

    for (const id of Array.from(scheduled)) {
      if (!ids.includes(id)) {
        scheduled.delete(id);
      }
    }
  },
  { immediate: true },
);
</script>

<template>
  <div class="pointer-events-none fixed right-4 top-16 z-50 flex max-w-[360px] flex-col gap-2">
    <transition-group name="toast">
      <div
        v-for="item in items"
        :key="item.id"
        class="pointer-events-auto flex items-start gap-3 rounded-xl border bg-white px-4 py-3 shadow-lg"
        :class="{
          'border-accent/20': item.type === 'info',
          'border-warn/20': item.type === 'warn',
          'border-danger/20': item.type === 'danger',
        }"
      >
        <div
          class="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-lg"
          :class="{
            'bg-accent-light text-accent': item.type === 'info',
            'bg-warn-light text-warn': item.type === 'warn',
            'bg-danger-light text-danger': item.type === 'danger',
          }"
        >
          <svg class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor">
            <path
              v-if="item.type === 'danger'"
              stroke-linecap="round"
              stroke-linejoin="round"
              d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z"
            />
            <path
              v-else-if="item.type === 'warn'"
              stroke-linecap="round"
              stroke-linejoin="round"
              d="M14.857 17.082a23.848 23.848 0 0 0 5.454-1.31A8.967 8.967 0 0 1 18 9.75V9A6 6 0 0 0 6 9v.75a8.967 8.967 0 0 1-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 0 1-5.714 0m5.714 0a3 3 0 1 1-5.714 0"
            />
            <path
              v-else
              stroke-linecap="round"
              stroke-linejoin="round"
              d="m11.25 11.25.041-.02a.75.75 0 0 1 1.063.852l-.708 2.836a.75.75 0 0 0 1.063.853l.041-.021M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9-3.75h.008v.008H12V8.25Z"
            />
          </svg>
        </div>

        <p class="flex-1 text-sm text-ink">{{ item.message }}</p>

        <button
          type="button"
          class="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-md text-ink-3 transition hover:bg-surface-3 hover:text-ink"
          @click="emit('dismiss', item.id)"
        >
          <svg class="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke-width="2.5" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" d="M6 18 18 6M6 6l12 12" />
          </svg>
        </button>
      </div>
    </transition-group>
  </div>
</template>

<style scoped>
.toast-enter-active {
  transition: all 0.3s ease-out;
}

.toast-leave-active {
  transition: all 0.2s ease-in;
}

.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translateX(100%);
}
</style>
