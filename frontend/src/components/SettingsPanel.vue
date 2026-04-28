<script setup lang="ts">
import { defineAsyncComponent } from "vue";
import { useI18n } from "vue-i18n";
import type { GoogleCalendarStatus, GoogleCalendarSyncResult, TravelEstimate, UserProfile, WeatherNow } from "@/stores/workspace";

const GoogleCalendarPanel = defineAsyncComponent(() => import("@/components/GoogleCalendarPanel.vue"));
const ProfilePanel = defineAsyncComponent(() => import("@/components/ProfilePanel.vue"));
const ContextPanel = defineAsyncComponent(() => import("@/components/ContextPanel.vue"));

const props = defineProps<{
  profile: UserProfile | null;
  savingProfile: boolean;
  googleCalendarStatus: GoogleCalendarStatus | null;
  googleCalendarSyncResult: GoogleCalendarSyncResult | null;
  googleCalendarFeedback: string | null;
  startingGoogleCalendarAuth: boolean;
  syncingGoogleCalendar: boolean;
  weatherNow: WeatherNow | null;
  travelEstimate: TravelEstimate | null;
  loading?: boolean;
}>();

const emit = defineEmits<{
  saveProfile: [payload: Partial<UserProfile>];
  connectGoogleCalendar: [];
  syncGoogleCalendar: [];
  dismissGoogleCalendarFeedback: [];
}>();

const { t } = useI18n();
</script>

<template>
  <div class="space-y-4">
    <div class="rounded-xl border border-border bg-white px-4 py-3 shadow-card">
      <p class="text-xs font-bold uppercase tracking-widest text-ink-3">{{ t("settings.title") }}</p>
    </div>

    <!-- Profile section -->
    <div class="rounded-xl border border-border bg-white p-4 shadow-card">
      <ProfilePanel
        :profile="profile"
        :saving="savingProfile"
        @save="emit('saveProfile', $event)"
      />
    </div>

    <!-- Google Calendar section -->
    <GoogleCalendarPanel
      :status="googleCalendarStatus"
      :sync-result="googleCalendarSyncResult"
      :feedback="googleCalendarFeedback"
      :starting-auth="startingGoogleCalendarAuth"
      :syncing="syncingGoogleCalendar"
      @connect="emit('connectGoogleCalendar')"
      @sync="emit('syncGoogleCalendar')"
      @dismiss-feedback="emit('dismissGoogleCalendarFeedback')"
    />

    <!-- Context / Weather + Commute (loaded on demand) -->
    <div>
      <p class="mb-2 text-xs font-semibold text-ink-3 px-1">{{ t("settings.context") }}</p>
      <ContextPanel
        :weather-now="weatherNow"
        :travel-estimate="travelEstimate"
        :loading="loading"
      />
    </div>
  </div>
</template>
