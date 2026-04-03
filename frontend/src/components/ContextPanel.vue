<script setup lang="ts">
import { useI18n } from "vue-i18n";
import LoadingSkeleton from "@/components/LoadingSkeleton.vue";
import type { TravelEstimate, WeatherNow } from "@/stores/workspace";
const { t } = useI18n();
defineProps<{ weatherNow: WeatherNow | null; travelEstimate: TravelEstimate | null; loading?: boolean }>();
</script>

<template>
  <div class="grid gap-3 sm:grid-cols-2">
    <!-- Weather -->
    <div class="rounded-xl border border-border bg-white p-4 shadow-card">
      <p class="text-[10px] font-bold uppercase tracking-widest text-ink-3">{{ t("contextPanel.weather") }}</p>
      <LoadingSkeleton v-if="loading" :lines="3" class-name="mt-3" />
      <div v-else-if="weatherNow" class="mt-2">
        <div class="flex items-baseline gap-1.5">
          <span class="text-3xl font-bold text-ink">{{ weatherNow.temp }}°</span>
          <span class="text-sm text-ink-3">{{ t("contextPanel.feelsLike", { value: weatherNow.feels_like }) }}</span>
        </div>
        <p class="mt-1 text-sm font-medium text-ink-2">{{ weatherNow.text }}</p>
        <p class="mt-0.5 text-xs text-ink-3">{{ weatherNow.location }} · {{ t("contextPanel.humidity", { value: weatherNow.humidity }) }} · {{ t("contextPanel.wind", { value: weatherNow.wind_scale }) }}</p>
      </div>
      <p v-else class="mt-2 text-sm text-ink-3">{{ t("contextPanel.locationNotSet") }}</p>
    </div>

    <!-- Commute -->
    <div class="rounded-xl border border-border bg-white p-4 shadow-card">
      <p class="text-[10px] font-bold uppercase tracking-widest text-ink-3">{{ t("contextPanel.commute") }}</p>
      <LoadingSkeleton v-if="loading" :lines="3" class-name="mt-3" />
      <div v-else-if="travelEstimate" class="mt-2">
        <div class="flex items-baseline gap-1.5">
          <span class="text-3xl font-bold text-ink">{{ travelEstimate.duration_minutes }}<span class="text-lg">min</span></span>
          <span class="text-sm text-ink-3">{{ travelEstimate.distance_km }} km</span>
        </div>
        <p class="mt-1 text-sm font-medium text-ink-2">{{ travelEstimate.origin }} → {{ travelEstimate.destination }}</p>
        <p class="mt-0.5 text-xs text-ink-3">{{ t("contextPanel.via", { mode: travelEstimate.mode }) }}</p>
      </div>
      <p v-else class="mt-2 text-sm text-ink-3">{{ t("contextPanel.profileNotSet") }}</p>
    </div>
  </div>
</template>
