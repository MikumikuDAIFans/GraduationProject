<script setup lang="ts">
import type { TravelEstimate, WeatherNow } from "@/stores/workspace";

defineProps<{
  weatherNow: WeatherNow | null;
  travelEstimate: TravelEstimate | null;
}>();
</script>

<template>
  <section class="rounded-2xl border border-white/70 bg-white/70 px-5 py-4 shadow-panel backdrop-blur-xl">
    <p class="mb-3 text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">Context</p>
    <div class="grid gap-3 md:grid-cols-2">

      <!-- Weather -->
      <div class="rounded-xl bg-sky-50 px-4 py-3">
        <p class="text-xs font-bold uppercase tracking-[0.18em] text-sky-600">Weather</p>
        <div v-if="weatherNow" class="mt-2">
          <div class="flex items-end gap-2">
            <span class="text-2xl font-bold text-ink">{{ weatherNow.temp }}°</span>
            <span class="mb-0.5 text-sm text-slate-500">feels {{ weatherNow.feels_like }}°</span>
          </div>
          <p class="mt-1 text-sm font-semibold text-ink">{{ weatherNow.text }}</p>
          <p class="mt-1 text-xs text-slate-400">{{ weatherNow.location }} · {{ weatherNow.humidity }}% humidity · wind {{ weatherNow.wind_scale }}</p>
        </div>
        <p v-else class="mt-2 text-sm text-slate-400">Not loaded yet.</p>
      </div>

      <!-- Commute -->
      <div class="rounded-xl bg-warn-light px-4 py-3">
        <p class="text-xs font-bold uppercase tracking-[0.18em] text-warn">Commute</p>
        <div v-if="travelEstimate" class="mt-2">
          <div class="flex items-end gap-2">
            <span class="text-2xl font-bold text-ink">{{ travelEstimate.duration_minutes }}'</span>
            <span class="mb-0.5 text-sm text-slate-500">{{ travelEstimate.distance_km }} km</span>
          </div>
          <p class="mt-1 text-sm font-semibold text-ink">{{ travelEstimate.origin }} → {{ travelEstimate.destination }}</p>
          <p class="mt-1 text-xs text-slate-400">via {{ travelEstimate.mode }}</p>
        </div>
        <p v-else class="mt-2 text-sm text-slate-400">Not loaded yet.</p>
      </div>

    </div>
  </section>
</template>
