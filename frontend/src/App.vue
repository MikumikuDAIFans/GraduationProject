<script setup lang="ts">
import { defineAsyncComponent, onBeforeUnmount, onMounted, ref } from "vue";
const CalendarPanel = defineAsyncComponent(() => import("@/components/CalendarPanel.vue"));
const AssistantPanel = defineAsyncComponent(() => import("@/components/AssistantPanel.vue"));
const ContextPanel = defineAsyncComponent(() => import("@/components/ContextPanel.vue"));
const GoogleCalendarPanel = defineAsyncComponent(() => import("@/components/GoogleCalendarPanel.vue"));
const InsightsPanel = defineAsyncComponent(() => import("@/components/InsightsPanel.vue"));
const ProfilePanel = defineAsyncComponent(() => import("@/components/ProfilePanel.vue"));
const SummaryPanel = defineAsyncComponent(() => import("@/components/SummaryPanel.vue"));
const ToastNotification = defineAsyncComponent(() => import("@/components/ToastNotification.vue"));
import { useWorkspaceStore } from "@/stores/workspace";

const workspace = useWorkspaceStore();
const profileOpen = ref(false);

type MobileTab = "summary" | "calendar" | "insights" | "assistant";
const mobileTab = ref<MobileTab>("summary");

const mobileTabs = [
  {
    key: "summary",
    label: "Overview",
    icon: "M9 12h3.75M9 15h3.75M9 18h3.75m3 .75H18a2.25 2.25 0 0 0 2.25-2.25V6.108c0-1.135-.845-2.098-1.976-2.192a48.424 48.424 0 0 0-1.123-.08m-5.801 0c-.065.21-.1.433-.1.664 0 .414.336.75.75.75h4.5a.75.75 0 0 0 .75-.75 2.25 2.25 0 0 0-.1-.664m-5.8 0A2.251 2.251 0 0 1 13.5 2.25H15c1.012 0 1.867.668 2.15 1.586m-5.8 0c-.376.023-.75.05-1.124.08C9.095 4.01 8.25 4.973 8.25 6.108V8.25m0 0H4.875c-.621 0-1.125.504-1.125 1.125v11.25c0 .621.504 1.125 1.125 1.125h9.75c.621 0 1.125-.504 1.125-1.125V9.375c0-.621-.504-1.125-1.125-1.125H8.25ZM6.75 12h.008v.008H6.75V12Zm0 3h.008v.008H6.75V15Zm0 3h.008v.008H6.75V18Z",
  },
  {
    key: "calendar",
    label: "Calendar",
    icon: "M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 0 1 2.25-2.25h13.5A2.25 2.25 0 0 1 21 7.5v11.25m-18 0A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75m-18 0v-7.5A2.25 2.25 0 0 1 5.25 9h13.5A2.25 2.25 0 0 1 21 11.25v7.5m-9-6h.008v.008H12v-.008ZM12 15h.008v.008H12V15Zm0 2.25h.008v.008H12v-.008ZM9.75 15h.008v.008H9.75V15Zm0 2.25h.008v.008H9.75v-.008ZM7.5 15h.008v.008H7.5V15Zm0 2.25h.008v.008H7.5v-.008Zm6.75-4.5h.008v.008h-.008v-.008Zm0 2.25h.008v.008h-.008V15Zm0 2.25h.008v.008h-.008v-.008Zm2.25-4.5h.008v.008H16.5v-.008Zm0 2.25h.008v.008H16.5V15Z",
  },
  {
    key: "insights",
    label: "Tasks",
    icon: "M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z",
  },
  {
    key: "assistant",
    label: "AI",
    icon: "M7.5 8.25h9m-9 3H12m-9.75 1.51c0 1.6 1.123 2.994 2.707 3.227 1.129.166 2.27.293 3.423.379.35.026.67.21.865.501L12 21l2.755-4.133a1.14 1.14 0 0 1 .865-.501 48.172 48.172 0 0 0 3.423-.379c1.584-.233 2.707-1.626 2.707-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0 0 12 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018Z",
  },
] as const;

function handleFocusTask(taskId: number) {
  workspace.focusTask(taskId);
  mobileTab.value = "insights";
}

function handleFocusEvent(eventId: number) {
  workspace.focusEvent(eventId);
  mobileTab.value = "calendar";
}

function handleFocusAssistant() {
  mobileTab.value = "assistant";
}

async function sendAndFocusAssistant(message: string) {
  mobileTab.value = "assistant";
  await workspace.sendAssistantMessage(message);
}

onMounted(() => {
  if (typeof window !== "undefined" && "Notification" in window && Notification.permission === "default") {
    void Notification.requestPermission();
  }
  if (typeof window !== "undefined" && window.location.pathname === "/auth/callback") {
    void workspace.handleGoogleCalendarCallback().finally(() => { void workspace.hydrate(); });
    return;
  }
  void workspace.hydrate();
});

onBeforeUnmount(() => { workspace.disconnectNotifications(); });
</script>

<template>
  <div class="min-h-screen bg-surface-2 font-body text-ink">
    <ToastNotification :items="workspace.toasts" @dismiss="workspace.dismissToast" />

    <!-- Google Auth overlay -->
    <div
      v-if="workspace.processingGoogleCalendarCallback"
      class="fixed inset-0 z-50 flex items-center justify-center bg-white/90 backdrop-blur-sm"
    >
      <div class="w-80 rounded-2xl border border-border bg-white p-8 text-center shadow-card-md">
        <div class="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-accent-light">
          <svg class="h-6 w-6 text-accent" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 0 1 2.25-2.25h13.5A2.25 2.25 0 0 1 21 7.5v11.25" />
          </svg>
        </div>
        <h2 class="text-base font-bold text-ink">Completing authorization…</h2>
        <p class="mt-1.5 text-sm text-ink-3">Connecting your Google Calendar</p>
      </div>
    </div>

    <!-- ═══ DESKTOP (xl+) ═══════════════════════════════════════ -->
    <div class="hidden xl:flex xl:h-screen xl:flex-col">

      <!-- Top nav -->
      <header class="flex h-14 shrink-0 items-center justify-between border-b border-border bg-white px-6">
        <div class="flex items-center gap-3">
          <div class="flex h-7 w-7 items-center justify-center rounded-lg bg-accent">
            <svg class="h-4 w-4 text-white" fill="currentColor" viewBox="0 0 20 20">
              <path fill-rule="evenodd" d="M5.75 2a.75.75 0 0 1 .75.75V4h7V2.75a.75.75 0 0 1 1.5 0V4h.25A2.75 2.75 0 0 1 18 6.75v8.5A2.75 2.75 0 0 1 15.25 18H4.75A2.75 2.75 0 0 1 2 15.25v-8.5A2.75 2.75 0 0 1 4.75 4H5V2.75A.75.75 0 0 1 5.75 2Z" clip-rule="evenodd"/>
            </svg>
          </div>
          <span class="text-sm font-bold text-ink">Daily Workspace</span>
        </div>

        <div class="flex items-center gap-2">
          <span class="rounded-lg bg-surface-3 px-2.5 py-1 text-xs font-medium text-ink-2">
            <span class="font-semibold text-ink">{{ workspace.events.length }}</span> events
          </span>
          <span class="rounded-lg bg-surface-3 px-2.5 py-1 text-xs font-medium text-ink-2">
            <span class="font-semibold text-ink">{{ workspace.tasks.length }}</span> tasks
          </span>
          <span
            class="rounded-lg px-2.5 py-1 text-xs font-medium"
            :class="workspace.assistantInboxUnreadTotal > 0
              ? 'bg-warn-light text-warn font-semibold'
              : 'bg-surface-3 text-ink-2'"
          >
            {{ workspace.assistantInboxUnreadTotal }} follow-ups
          </span>
          <div class="mx-1 h-4 w-px bg-border" />
          <button
            type="button"
            class="flex items-center gap-1.5 rounded-lg border border-border bg-white px-3 py-1.5 text-xs font-medium text-ink-2 transition hover:bg-surface-3"
            @click="profileOpen = !profileOpen"
          >
            <svg class="h-3.5 w-3.5 text-ink-3" fill="currentColor" viewBox="0 0 20 20">
              <path d="M10 8a3 3 0 1 0 0-6 3 3 0 0 0 0 6ZM3.465 14.493a1.23 1.23 0 0 0 .41 1.412A9.957 9.957 0 0 0 10 18c2.31 0 4.438-.784 6.131-2.095a1.23 1.23 0 0 0 .41-1.412 9.96 9.96 0 0 0-6.54-6.18 1.23 1.23 0 0 0-.81-.004 9.96 9.96 0 0 0-6.727 6.184Z"/>
            </svg>
            {{ workspace.profile?.display_name || "Profile" }}
          </button>
        </div>
      </header>

      <!-- Profile slide-in -->
      <div v-if="profileOpen" class="shrink-0 border-b border-border bg-white px-6 py-4">
        <ProfilePanel :profile="workspace.profile" :saving="workspace.savingProfile" @save="workspace.saveProfile" />
      </div>

      <!-- Main 2-col content -->
      <div class="flex min-h-0 flex-1 overflow-hidden">

        <!-- Left scrollable column -->
        <div class="flex-1 overflow-y-auto">
          <div class="mx-auto max-w-3xl space-y-4 px-6 py-5">
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
            <ContextPanel :weather-now="workspace.weatherNow" :travel-estimate="workspace.travelEstimate" />
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

        <!-- Right fixed Assistant column -->
        <div class="flex w-[400px] shrink-0 flex-col border-l border-border bg-white">
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

    <!-- ═══ MOBILE (<xl) ═════════════════════════════════════════ -->
    <div class="flex h-dvh flex-col xl:hidden">

      <!-- Mobile top bar -->
      <header class="flex h-12 shrink-0 items-center justify-between border-b border-border bg-white px-4">
        <div class="flex items-center gap-2">
          <div class="flex h-6 w-6 items-center justify-center rounded-md bg-accent">
            <svg class="h-3.5 w-3.5 text-white" fill="currentColor" viewBox="0 0 20 20">
              <path fill-rule="evenodd" d="M5.75 2a.75.75 0 0 1 .75.75V4h7V2.75a.75.75 0 0 1 1.5 0V4h.25A2.75 2.75 0 0 1 18 6.75v8.5A2.75 2.75 0 0 1 15.25 18H4.75A2.75 2.75 0 0 1 2 15.25v-8.5A2.75 2.75 0 0 1 4.75 4H5V2.75A.75.75 0 0 1 5.75 2Z" clip-rule="evenodd"/>
            </svg>
          </div>
          <span class="text-sm font-bold text-ink">Daily Workspace</span>
        </div>
        <div class="flex items-center gap-2">
          <span
            v-if="workspace.assistantInboxUnreadTotal > 0"
            class="rounded-full bg-warn px-1.5 py-0.5 text-[10px] font-bold text-white"
          >{{ workspace.assistantInboxUnreadTotal }}</span>
          <button
            type="button"
            class="flex h-7 w-7 items-center justify-center rounded-lg border border-border bg-white text-ink-3 transition hover:bg-surface-3"
            @click="profileOpen = !profileOpen"
          >
            <svg class="h-4 w-4" fill="currentColor" viewBox="0 0 20 20">
              <path d="M10 8a3 3 0 1 0 0-6 3 3 0 0 0 0 6ZM3.465 14.493a1.23 1.23 0 0 0 .41 1.412A9.957 9.957 0 0 0 10 18c2.31 0 4.438-.784 6.131-2.095a1.23 1.23 0 0 0 .41-1.412 9.96 9.96 0 0 0-6.54-6.18 1.23 1.23 0 0 0-.81-.004 9.96 9.96 0 0 0-6.727 6.184Z"/>
            </svg>
          </button>
        </div>
      </header>

      <!-- Profile drawer -->
      <div v-if="profileOpen" class="shrink-0 border-b border-border bg-white px-4 py-3">
        <ProfilePanel :profile="workspace.profile" :saving="workspace.savingProfile" @save="workspace.saveProfile" />
      </div>

      <!-- Tab content — takes all remaining height -->
      <div class="min-h-0 flex-1 overflow-y-auto bg-surface-2">
        <div v-if="mobileTab === 'summary'" class="space-y-3 p-4">
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

        <div v-else-if="mobileTab === 'calendar'" class="p-4">
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

        <div v-else-if="mobileTab === 'insights'" class="p-4">
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

        <!-- Assistant tab: fill full height via flex -->
        <div v-else-if="mobileTab === 'assistant'" class="flex h-full flex-col">
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

      <!-- Bottom Tab bar -->
      <nav class="flex h-14 shrink-0 border-t border-border bg-white">
        <button
          v-for="tab in mobileTabs"
          :key="tab.key"
          type="button"
          class="relative flex flex-1 flex-col items-center justify-center gap-0.5 text-[10px] font-semibold transition-colors"
          :class="mobileTab === tab.key ? 'text-accent' : 'text-ink-3'"
          @click="mobileTab = tab.key as MobileTab"
        >
          <span
            v-if="mobileTab === tab.key"
            class="absolute top-0 left-1/2 h-0.5 w-8 -translate-x-1/2 rounded-full bg-accent"
          />
          <svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke-width="1.8" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" :d="tab.icon" />
          </svg>
          {{ tab.label }}
          <span
            v-if="tab.key === 'assistant' && workspace.assistantInboxUnreadTotal > 0"
            class="absolute right-3 top-2 flex h-4 w-4 items-center justify-center rounded-full bg-warn text-[9px] font-bold text-white"
          >{{ workspace.assistantInboxUnreadTotal }}</span>
        </button>
      </nav>

    </div>
  </div>
</template>
