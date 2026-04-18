<script setup lang="ts">
import { onErrorCaptured, ref } from "vue";
import { useI18n } from "vue-i18n";

const { t } = useI18n();
const error = ref<unknown>(null);

onErrorCaptured((captured) => {
  error.value = captured;
  return false;
});

function reloadPage() {
  if (typeof window !== "undefined") {
    window.location.reload();
  }
}
</script>

<template>
  <slot v-if="!error" />
  <div v-else class="flex min-h-screen items-center justify-center bg-surface-2 p-6">
    <div class="w-full max-w-md rounded-2xl border border-danger/20 bg-white p-6 shadow-card-md">
      <p class="text-sm font-bold text-danger">{{ t("errorBoundary.title") }}</p>
      <p class="mt-2 text-sm text-ink-3">{{ t("errorBoundary.description") }}</p>
      <div v-if="error" class="mt-4 rounded-lg bg-red-50 p-3 text-xs font-mono text-red-700 break-all">
        <p class="font-bold mb-1">Error Details:</p>
        <p>{{ String(error) }}</p>
      </div>
      <button
        type="button"
        class="mt-4 rounded-xl bg-ink px-4 py-2 text-sm font-semibold text-white transition hover:bg-ink-2"
        @click="reloadPage"
      >
        {{ t("errorBoundary.reload") }}
      </button>
    </div>
  </div>
</template>
