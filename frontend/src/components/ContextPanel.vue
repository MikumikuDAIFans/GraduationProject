<script setup lang="ts">
import type { TravelEstimate, WeatherNow } from "@/stores/workspace";
defineProps<{ weatherNow: WeatherNow | null; travelEstimate: TravelEstimate | null }>();
</script>

<template>
  <div class="grid gap-3 sm:grid-cols-2">
    <!-- Weather -->
    <div class="rounded-xl border border-border bg-white p-4 shadow-card">
      <p class="text-[10px] font-bold uppercase tracking-widest text-ink-3">Weather</p>
      <div v-if="weatherNow" class="mt-2">
        <div class="flex items-baseline gap-1.5">
          <span class="text-3xl font-bold text-ink">{{ weatherNow.temp }}°</span>
          <span class="text-sm text-ink-3">feels {{ weatherNow.feels_like }}°</span>
        </div>
        <p class="mt-1 text-sm font-medium text-ink-2">{{ weatherNow.text }}</p>
        <p class="mt-0.5 text-xs text-ink-3">{{ weatherNow.location }} · {{ weatherNow.humidity }}% hum · wind {{ weatherNow.wind_scale }}</p>
      </div>
      <p v-else class="mt-2 text-sm text-ink-3">Location not set.</p>
    </div>

    <!-- Commute -->
    <div class="rounded-xl border border-border bg-white p-4 shadow-card">
      <p class="text-[10px] font-bold uppercase tracking-widest text-ink-3">Commute</p>
      <div v-if="travelEstimate" class="mt-2">
        <div class="flex items-baseline gap-1.5">
          <span class="text-3xl font-bold text-ink">{{ travelEstimate.duration_minutes }}<span class="text-lg">min</span></span>
          <span class="text-sm text-ink-3">{{ travelEstimate.distance_km }} km</span>
        </div>
        <p class="mt-1 text-sm font-medium text-ink-2">{{ travelEstimate.origin }} → {{ travelEstimate.destination }}</p>
        <p class="mt-0.5 text-xs text-ink-3">via {{ travelEstimate.mode }}</p>
      </div>
      <p v-else class="mt-2 text-sm text-ink-3">Profile not set.</p>
    </div>
  </div>
</template>
