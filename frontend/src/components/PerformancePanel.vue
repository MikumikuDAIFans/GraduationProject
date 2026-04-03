<script setup lang="ts">
import { useI18n } from "vue-i18n";
import { formatDateTime } from "@/utils/locale";

interface PerformancePath {
  path: string;
  count: number;
}

interface PerformanceMetrics {
  uptime_seconds: number;
  request_count: number;
  last_request_ms: number;
  avg_request_ms: number;
  p95_request_ms: number;
  hottest_paths: PerformancePath[];
}

interface AIHealth {
  enabled: boolean;
  provider: string;
  circuit_open: boolean;
  circuit_open_until?: string | null;
  consecutive_failures: number;
}

interface FrontendPerformance {
  first_paint_ms?: number | null;
  first_contentful_paint_ms?: number | null;
  largest_contentful_paint_ms?: number | null;
}

defineProps<{
  metrics: PerformanceMetrics | null;
  aiHealth: AIHealth | null;
  frontendMetrics: FrontendPerformance | null;
  loading: boolean;
}>();

const { t, locale } = useI18n();

function uptimeLabel(seconds: number | undefined) {
  if (!seconds) return "0m";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
}

function backendTone(avg: number | undefined) {
  if (!avg || avg < 400) return { label: t("performance.warningFast"), cls: "text-positive bg-positive-light" };
  if (avg < 1200) return { label: t("performance.warningNormal"), cls: "text-accent bg-accent-light" };
  return { label: t("performance.warningSlow"), cls: "text-danger bg-danger-light" };
}

function paintTone(fcp: number | undefined) {
  if (!fcp || fcp < 1200) return { label: t("performance.warningFast"), cls: "text-positive bg-positive-light" };
  if (fcp < 2500) return { label: t("performance.warningNormal"), cls: "text-accent bg-accent-light" };
  return { label: t("performance.warningSlow"), cls: "text-danger bg-danger-light" };
}
</script>

<template>
  <div class="rounded-xl border border-border bg-white p-4 shadow-card">
    <div class="flex items-center justify-between">
      <div>
        <p class="text-[10px] font-bold uppercase tracking-widest text-ink-3">{{ t("performance.title") }}</p>
        <h2 class="mt-0.5 text-sm font-bold text-ink">{{ t("performance.subtitle") }}</h2>
      </div>
      <span
        class="rounded-md px-2 py-1 text-[11px] font-semibold"
        :class="aiHealth?.circuit_open ? 'bg-danger-light text-danger' : 'bg-positive-light text-positive'"
      >
        {{ aiHealth?.circuit_open ? t("performance.aiCircuitOpen") : t("performance.aiHealthy") }}
      </span>
    </div>

    <div v-if="loading" class="mt-4 animate-pulse space-y-3">
      <div class="h-3 w-2/3 rounded-full bg-surface-3" />
      <div class="grid gap-3 sm:grid-cols-3">
        <div class="h-16 rounded-xl bg-surface-3" />
        <div class="h-16 rounded-xl bg-surface-3" />
        <div class="h-16 rounded-xl bg-surface-3" />
      </div>
    </div>

    <div v-else class="mt-4 grid gap-3 sm:grid-cols-3">
      <div class="rounded-xl border border-border bg-surface-2 p-3">
        <div class="flex items-center justify-between gap-2">
          <p class="text-[10px] uppercase tracking-widest text-ink-3">{{ t("performance.backendAvg") }}</p>
          <span class="rounded-md px-2 py-0.5 text-[10px] font-semibold" :class="backendTone(metrics?.avg_request_ms).cls">
            {{ backendTone(metrics?.avg_request_ms).label }}
          </span>
        </div>
        <p class="mt-1 text-lg font-bold text-ink">{{ metrics?.avg_request_ms ?? 0 }} ms</p>
        <p class="text-xs text-ink-3">{{ t("performance.p95", { value: metrics?.p95_request_ms ?? 0 }) }}</p>
      </div>
      <div class="rounded-xl border border-border bg-surface-2 p-3">
        <div class="flex items-center justify-between gap-2">
          <p class="text-[10px] uppercase tracking-widest text-ink-3">{{ t("performance.frontendPaint") }}</p>
          <span class="rounded-md px-2 py-0.5 text-[10px] font-semibold" :class="paintTone(frontendMetrics?.first_contentful_paint_ms ?? undefined).cls">
            {{ paintTone(frontendMetrics?.first_contentful_paint_ms ?? undefined).label }}
          </span>
        </div>
        <p class="mt-1 text-lg font-bold text-ink">{{ frontendMetrics?.first_contentful_paint_ms ?? 0 }} ms</p>
        <p class="text-xs text-ink-3">{{ t("performance.lcp", { value: frontendMetrics?.largest_contentful_paint_ms ?? 0 }) }}</p>
      </div>
      <div class="rounded-xl border border-border bg-surface-2 p-3">
        <p class="text-[10px] uppercase tracking-widest text-ink-3">{{ t("performance.uptime") }}</p>
        <p class="mt-1 text-lg font-bold text-ink">{{ uptimeLabel(metrics?.uptime_seconds) }}</p>
        <p class="text-xs text-ink-3">{{ t("performance.requests", { count: metrics?.request_count ?? 0 }) }}</p>
      </div>
    </div>

    <div v-if="aiHealth?.circuit_open && aiHealth.circuit_open_until" class="mt-4 rounded-lg border border-danger/20 bg-danger-light px-3 py-2 text-xs text-danger">
      {{ t("performance.circuitUntil", { time: formatDateTime(aiHealth.circuit_open_until, locale) }) }}
    </div>

    <div v-if="metrics?.hottest_paths?.length" class="mt-4">
      <p class="text-[10px] font-bold uppercase tracking-widest text-ink-3">{{ t("performance.hotPaths") }}</p>
      <div class="mt-2 space-y-2">
        <div
          v-for="item in metrics.hottest_paths"
          :key="item.path"
          class="flex items-center justify-between rounded-lg border border-border bg-surface-2 px-3 py-2 text-xs"
        >
          <span class="truncate text-ink">{{ item.path }}</span>
          <span class="text-ink-3">{{ item.count }}</span>
        </div>
      </div>
    </div>
  </div>
</template>
