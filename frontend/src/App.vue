<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";
import CalendarPanel from "@/components/CalendarPanel.vue";
import AssistantPanel from "@/components/AssistantPanel.vue";
import ContextPanel from "@/components/ContextPanel.vue";
import GoogleCalendarPanel from "@/components/GoogleCalendarPanel.vue";
import InsightsPanel from "@/components/InsightsPanel.vue";
import ProfilePanel from "@/components/ProfilePanel.vue";
import SummaryPanel from "@/components/SummaryPanel.vue";
import { useWorkspaceStore } from "@/stores/workspace";

const workspace = useWorkspaceStore();

const calendarRef = ref<HTMLElement | null>(null);
const insightsRef = ref<HTMLElement | null>(null);
const assistantRef = ref<HTMLElement | null>(null);
const profileOpen = ref(false);

type MobileTab = "summary" | "calendar" | "insights" | "assistant";
const mobileTab = ref<MobileTab>("summary");

function scrollTo(el: HTMLElement | null) {
  if (!el) return;
  el.scrollIntoView({ behavior: "smooth", block: "start" });
}

function handleFocusTask(taskId: number) {
  workspace.focusTask(taskId);
  mobileTab.value = "insights";
  scrollTo(insightsRef.value);
}

function handleFocusEvent(eventId: number) {
  workspace.focusEvent(eventId);
  mobileTab.value = "calendar";
  scrollTo(calendarRef.value);
}

function handleFocusAssistant() {
  mobileTab.value = "assistant";
  scrollTo(assistantRef.value);
}

async function sendAndFocusAssistant(message: string) {
  mobileTab.value = "assistant";
  scrollTo(assistantRef.value);
  await workspace.sendAssistantMessage(message);
}

onMounted(() => {
  if (typeof window !== "undefined" && "Notification" in window && Notification.permission === "default") {
    void Notification.requestPermission();
  }
  if (typeof window !== "undefined" && window.location.pathname === "/auth/callback") {
    void workspace.handleGoogleCalendarCallback().finally(() => {
      void workspace.hydrate();
    });
    return;
  }
  void workspace.hydrate();
});

onBeforeUnmount(() => {
  workspace.disconnectNotifications();
});
</script>

<template>
  <div class="min-h-screen bg-hero-wash font-body text-ink">
    <!-- Google Auth Callback Banner -->
    <div
      v-if="workspace.processingGoogleCalendarCallback"
      class="fixed inset-0 z-50 flex items-center justify-center bg-white/80 backdrop-blur-md"
    >
      <div class="rounded-2xl border border-slate-200 bg-white px-10 py-10 text-center shadow-xl">
        <p class="text-xs font-semibold uppercase tracking-[0.3em] text-accent">Google Calendar</p>
        <h2 class="mt-3 text-2xl font-bold text-ink">Completing authorization…</h2>
        <p class="mx-auto mt-3 max-w-sm text-sm leading-6 text-slate-500">
          Exchanging authorization code and restoring your workspace.
        </p>
      </div>
    </div>

    <!-- Mobile bottom-tab layout wrapper -->
    <div class="flex min-h-screen flex-col xl:block">

      <!-- ===== DESKTOP layout ===== -->
      <div class="hidden xl:block">
        <div class="mx-auto max-w-[1600px] px-8 py-5">
          <!-- Top nav bar -->
          <header class="mb-5 flex items-center justify-between gap-4 rounded-2xl border border-white/70 bg-white/70 px-5 py-3 shadow-panel backdrop-blur-xl">
            <div class="flex items-center gap-3">
              <div class="flex h-8 w-8 items-center justify-center rounded-xl bg-accent text-white">
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="h-4 w-4">
                  <path fill-rule="evenodd" d="M5.75 2a.75.75 0 0 1 .75.75V4h7V2.75a.75.75 0 0 1 1.5 0V4h.25A2.75 2.75 0 0 1 18 6.75v8.5A2.75 2.75 0 0 1 15.25 18H4.75A2.75 2.75 0 0 1 2 15.25v-8.5A2.75 2.75 0 0 1 4.75 4H5V2.75A.75.75 0 0 1 5.75 2Z" clip-rule="evenodd" />
                </svg>
              </div>
              <span class="text-base font-bold text-ink">Daily Workspace</span>
            </div>
            <div class="flex items-center gap-2">
              <span class="rounded-xl bg-slate-100 px-3 py-1.5 text-xs font-semibold text-slate-600">
                <span class="font-bold text-ink">{{ workspace.events.length }}</span> events
              </span>
              <span class="rounded-xl bg-slate-100 px-3 py-1.5 text-xs font-semibold text-slate-600">
                <span class="font-bold text-ink">{{ workspace.tasks.length }}</span> tasks
              </span>
              <span
                class="rounded-xl px-3 py-1.5 text-xs font-semibold"
                :class="workspace.assistantInboxUnreadTotal > 0 ? 'bg-warn-light text-warn font-bold' : 'bg-slate-100 text-slate-600'"
              >
                <span class="font-bold" :class="workspace.assistantInboxUnreadTotal > 0 ? 'text-warn' : 'text-ink'">{{ workspace.assistantInboxUnreadTotal }}</span> follow-ups
              </span>
            </div>
            <button
              type="button"
              class="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-600 transition hover:border-accent/30 hover:bg-accent-light hover:text-accent"
              @click="profileOpen = !profileOpen"
            >
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="h-3.5 w-3.5">
                <path d="M10 8a3 3 0 1 0 0-6 3 3 0 0 0 0 6ZM3.465 14.493a1.23 1.23 0 0 0 .41 1.412A9.957 9.957 0 0 0 10 18c2.31 0 4.438-.784 6.131-2.095a1.23 1.23 0 0 0 .41-1.412 9.96 9.96 0 0 0-6.54-6.18 1.23 1.23 0 0 0-.81-.004 9.96 9.96 0 0 0-6.727 6.184Z" />
              </svg>
              {{ workspace.profile?.display_name || "Profile" }}
            </button>
          </header>

          <div v-if="profileOpen" class="mb-5">
            <ProfilePanel :profile="workspace.profile" :saving="workspace.savingProfile" @save="workspace.saveProfile" />
          </div>

          <div class="grid gap-5 xl:grid-cols-[1fr_420px]">
            <div class="min-w-0 space-y-5">
              <GoogleCalendarPanel
                :status="workspace.googleCalendarStatus"
                :sync-result="workspace.googleCalendarSyncResult"
                :feedback="workspace.googleCalendarFeedback"
                :starting-auth="workspace.startingGoogleCalendarAuth"
                :syncing="workspace.syncingGoogleCalendar"
                @connect="workspace.startGoogleCalendarAuth"
                @sync="workspace.syncGoogleCalendar"
                @dismiss-feedback="workspace.clearGoogleCalendarFeedback"
              />
              <SummaryPanel
                :summary="workspace.assistantSummary"
                @send="sendAndFocusAssistant"
                @focus-task="handleFocusTask"
                @focus-event="handleFocusEvent"
                @focus-assistant="handleFocusAssistant"
              />
              <div ref="calendarRef">
                <CalendarPanel
                  :events="workspace.events"
                  :tasks="workspace.tasks"
                  :loading="workspace.loading"
                  :focused-event-id="workspace.focusedEventId"
                  :focused-task-id="workspace.focusedTaskId"
                  :mobile="false"
                  @update-status="workspace.updateEventStatus"
                  @send-assistant="sendAndFocusAssistant"
                  @delete-event="workspace.deleteEvent"
                />
              </div>
              <ContextPanel :weather-now="workspace.weatherNow" :travel-estimate="workspace.travelEstimate" />
              <div ref="insightsRef">
                <InsightsPanel
                  :reminders="workspace.reminders"
                  :today-suggestions="workspace.todaySuggestions"
                  :next-suggestions="workspace.nextSuggestions"
                  :tasks="workspace.tasks"
                  :focused-task-id="workspace.focusedTaskId"
                  @send="sendAndFocusAssistant"
                  @delete-task="workspace.deleteTask"
                />
              </div>
            </div>
            <div ref="assistantRef" class="xl:sticky xl:top-5 xl:self-start">
              <AssistantPanel
                :inbox-items="workspace.assistantInbox"
                :inbox-unread-total="workspace.assistantInboxUnreadTotal"
                :messages="workspace.messages"
                :sending="workspace.sending"
                :last-assistant-actions="workspace.lastAssistantActions"
                @send="workspace.sendAssistantMessage"
                @update-inbox="workspace.updateInboxItem"
                @focus-task="handleFocusTask"
              />
            </div>
          </div>
        </div>
      </div>

      <!-- ===== MOBILE layout ===== -->
      <div class="flex flex-1 flex-col xl:hidden">

        <!-- Mobile top bar -->
        <header class="sticky top-0 z-30 flex items-center justify-between border-b border-white/60 bg-white/85 px-4 py-3 backdrop-blur-xl">
          <div class="flex items-center gap-2.5">
            <div class="flex h-7 w-7 items-center justify-center rounded-lg bg-accent text-white">
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="h-3.5 w-3.5">
                <path fill-rule="evenodd" d="M5.75 2a.75.75 0 0 1 .75.75V4h7V2.75a.75.75 0 0 1 1.5 0V4h.25A2.75 2.75 0 0 1 18 6.75v8.5A2.75 2.75 0 0 1 15.25 18H4.75A2.75 2.75 0 0 1 2 15.25v-8.5A2.75 2.75 0 0 1 4.75 4H5V2.75A.75.75 0 0 1 5.75 2Z" clip-rule="evenodd" />
              </svg>
            </div>
            <span class="text-sm font-bold text-ink">Daily Workspace</span>
          </div>
          <div class="flex items-center gap-2">
            <span
              v-if="workspace.assistantInboxUnreadTotal > 0"
              class="rounded-full bg-warn px-2 py-0.5 text-[11px] font-bold text-white"
            >
              {{ workspace.assistantInboxUnreadTotal }}
            </span>
            <button
              type="button"
              class="flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-500 transition hover:bg-accent-light hover:text-accent"
              @click="profileOpen = !profileOpen"
            >
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="h-4 w-4">
                <path d="M10 8a3 3 0 1 0 0-6 3 3 0 0 0 0 6ZM3.465 14.493a1.23 1.23 0 0 0 .41 1.412A9.957 9.957 0 0 0 10 18c2.31 0 4.438-.784 6.131-2.095a1.23 1.23 0 0 0 .41-1.412 9.96 9.96 0 0 0-6.54-6.18 1.23 1.23 0 0 0-.81-.004 9.96 9.96 0 0 0-6.727 6.184Z" />
              </svg>
            </button>
          </div>
        </header>

        <!-- Mobile profile drawer -->
        <div v-if="profileOpen" class="border-b border-slate-100 bg-white/90 px-4 py-4 backdrop-blur">
          <ProfilePanel :profile="workspace.profile" :saving="workspace.savingProfile" @save="workspace.saveProfile" />
        </div>

        <!-- Mobile panel content -->
        <div class="flex-1 overflow-y-auto pb-20">

          <!-- Summary tab -->
          <div v-if="mobileTab === 'summary'" class="space-y-4 p-4">
            <GoogleCalendarPanel
              :status="workspace.googleCalendarStatus"
              :sync-result="workspace.googleCalendarSyncResult"
              :feedback="workspace.googleCalendarFeedback"
              :starting-auth="workspace.startingGoogleCalendarAuth"
              :syncing="workspace.syncingGoogleCalendar"
              @connect="workspace.startGoogleCalendarAuth"
              @sync="workspace.syncGoogleCalendar"
              @dismiss-feedback="workspace.clearGoogleCalendarFeedback"
            />
            <SummaryPanel
              :summary="workspace.assistantSummary"
              @send="sendAndFocusAssistant"
              @focus-task="handleFocusTask"
              @focus-event="handleFocusEvent"
              @focus-assistant="handleFocusAssistant"
            />
            <ContextPanel :weather-now="workspace.weatherNow" :travel-estimate="workspace.travelEstimate" />
          </div>

          <!-- Calendar tab -->
          <div v-if="mobileTab === 'calendar'" class="p-4">
            <CalendarPanel
              :events="workspace.events"
              :tasks="workspace.tasks"
              :loading="workspace.loading"
              :focused-event-id="workspace.focusedEventId"
              :focused-task-id="workspace.focusedTaskId"
              :mobile="true"
              @update-status="workspace.updateEventStatus"
              @send-assistant="sendAndFocusAssistant"
              @delete-event="workspace.deleteEvent"
            />
          </div>

          <!-- Insights tab -->
          <div v-if="mobileTab === 'insights'" class="p-4">
            <InsightsPanel
              :reminders="workspace.reminders"
              :today-suggestions="workspace.todaySuggestions"
              :next-suggestions="workspace.nextSuggestions"
              :tasks="workspace.tasks"
              :focused-task-id="workspace.focusedTaskId"
              @send="sendAndFocusAssistant"
              @delete-task="workspace.deleteTask"
            />
          </div>

          <!-- Assistant tab -->
          <div v-if="mobileTab === 'assistant'" class="p-4">
            <AssistantPanel
              :inbox-items="workspace.assistantInbox"
              :inbox-unread-total="workspace.assistantInboxUnreadTotal"
              :messages="workspace.messages"
              :sending="workspace.sending"
              :last-assistant-actions="workspace.lastAssistantActions"
              @send="workspace.sendAssistantMessage"
              @update-inbox="workspace.updateInboxItem"
              @focus-task="handleFocusTask"
            />
          </div>

        </div>

        <!-- Mobile bottom tab bar -->
        <nav class="fixed bottom-0 left-0 right-0 z-30 flex border-t border-slate-200/80 bg-white/95 backdrop-blur-xl">
          <button
            v-for="tab in [
              { key: 'summary', label: 'Summary', icon: 'M9 12h3.75M9 15h3.75M9 18h3.75m3 .75H18a2.25 2.25 0 0 0 2.25-2.25V6.108c0-1.135-.845-2.098-1.976-2.192a48.424 48.424 0 0 0-1.123-.08m-5.801 0c-.065.21-.1.433-.1.664 0 .414.336.75.75.75h4.5a.75.75 0 0 0 .75-.75 2.25 2.25 0 0 0-.1-.664m-5.8 0A2.251 2.251 0 0 1 13.5 2.25H15c1.012 0 1.867.668 2.15 1.586m-5.8 0c-.376.023-.75.05-1.124.08C9.095 4.01 8.25 4.973 8.25 6.108V8.25m0 0H4.875c-.621 0-1.125.504-1.125 1.125v11.25c0 .621.504 1.125 1.125 1.125h9.75c.621 0 1.125-.504 1.125-1.125V9.375c0-.621-.504-1.125-1.125-1.125H8.25ZM6.75 12h.008v.008H6.75V12Zm0 3h.008v.008H6.75V15Zm0 3h.008v.008H6.75V18Z' },
              { key: 'calendar', label: 'Calendar', icon: 'M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 0 1 2.25-2.25h13.5A2.25 2.25 0 0 1 21 7.5v11.25m-18 0A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75m-18 0v-7.5A2.25 2.25 0 0 1 5.25 9h13.5A2.25 2.25 0 0 1 21 11.25v7.5m-9-6h.008v.008H12v-.008ZM12 15h.008v.008H12V15Zm0 2.25h.008v.008H12v-.008ZM9.75 15h.008v.008H9.75V15Zm0 2.25h.008v.008H9.75v-.008ZM7.5 15h.008v.008H7.5V15Zm0 2.25h.008v.008H7.5v-.008Zm6.75-4.5h.008v.008h-.008v-.008Zm0 2.25h.008v.008h-.008V15Zm0 2.25h.008v.008h-.008v-.008Zm2.25-4.5h.008v.008H16.5v-.008Zm0 2.25h.008v.008H16.5V15Z' },
              { key: 'insights', label: 'Insights', icon: 'M3.75 3v11.25A2.25 2.25 0 0 0 6 16.5h2.25M3.75 3h-1.5m1.5 0h16.5m0 0h1.5m-1.5 0v11.25A2.25 2.25 0 0 1 18 16.5h-2.25m-7.5 0h7.5m-7.5 0-1 3m8.5-3 1 3m0 0 .5 1.5m-.5-1.5h-9.5m0 0-.5 1.5m.75-9 3-3 2.148 2.148A12.061 12.061 0 0 1 16.5 7.605' },
              { key: 'assistant', label: 'AI', icon: 'M7.5 8.25h9m-9 3H12m-9.75 1.51c0 1.6 1.123 2.994 2.707 3.227 1.129.166 2.27.293 3.423.379.35.026.67.21.865.501L12 21l2.755-4.133a1.14 1.14 0 0 1 .865-.501 48.172 48.172 0 0 0 3.423-.379c1.584-.233 2.707-1.626 2.707-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0 0 12 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018Z' },
            ]"
            :key="tab.key"
            type="button"
            class="relative flex flex-1 flex-col items-center gap-1 py-2.5 text-[10px] font-semibold transition-colors"
            :class="mobileTab === tab.key ? 'text-accent' : 'text-slate-400'"
            @click="mobileTab = tab.key as MobileTab"
          >
            <!-- Active indicator -->
            <span
              v-if="mobileTab === tab.key"
              class="absolute top-0 left-1/2 h-0.5 w-8 -translate-x-1/2 rounded-full bg-accent"
            />
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.8" stroke="currentColor" class="h-5 w-5">
              <path stroke-linecap="round" stroke-linejoin="round" :d="tab.icon" />
            </svg>
            {{ tab.label }}
            <!-- Unread badge on AI tab -->
            <span
              v-if="tab.key === 'assistant' && workspace.assistantInboxUnreadTotal > 0"
              class="absolute right-3 top-1.5 flex h-4 w-4 items-center justify-center rounded-full bg-warn text-[9px] font-bold text-white"
            >
              {{ workspace.assistantInboxUnreadTotal }}
            </span>
          </button>
        </nav>

      </div>
    </div>
  </div>
</template>
