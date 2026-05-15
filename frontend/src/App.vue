<script setup lang="ts">
import { computed, defineAsyncComponent, onBeforeUnmount, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";

const CalendarPanel = defineAsyncComponent(() => import("@/components/CalendarPanel.vue"));
const AssistantPanel = defineAsyncComponent(() => import("@/components/AssistantPanel.vue"));
const TasksPanel = defineAsyncComponent(() => import("@/components/TasksPanel.vue"));
const SettingsPanel = defineAsyncComponent(() => import("@/components/SettingsPanel.vue"));
const ErrorBoundary = defineAsyncComponent(() => import("@/components/ErrorBoundary.vue"));
const ToastNotification = defineAsyncComponent(() => import("@/components/ToastNotification.vue"));

import { useWorkspaceStore } from "@/stores/workspace";

const workspace = useWorkspaceStore();
const { t, locale } = useI18n();

type MobileTab = "calendar" | "tasks" | "assistant" | "settings";
const mobileTab = ref<MobileTab>("calendar");

const mobileTabs = computed<Array<{ key: MobileTab; label: string; icon: string }>>(() => [
  {
    key: "calendar",
    label: t("common.calendar"),
    icon: "M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 0 1 2.25-2.25h13.5A2.25 2.25 0 0 1 21 7.5v11.25m-18 0A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75m-18 0v-7.5A2.25 2.25 0 0 1 5.25 9h13.5A2.25 2.25 0 0 1 21 11.25v7.5m-9-6h.008v.008H12v-.008ZM12 15h.008v.008H12V15Zm0 2.25h.008v.008H12v-.008ZM9.75 15h.008v.008H9.75V15Zm0 2.25h.008v.008H9.75v-.008ZM7.5 15h.008v.008H7.5V15Zm0 2.25h.008v.008H7.5v-.008Zm6.75-4.5h.008v.008h-.008v-.008Zm0 2.25h.008v.008h-.008V15Zm0 2.25h.008v.008h-.008v-.008Zm2.25-4.5h.008v.008H16.5v-.008Zm0 2.25h.008v.008H16.5V15Z",
  },
  {
    key: "tasks",
    label: t("common.tasks"),
    icon: "M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z",
  },
  {
    key: "assistant",
    label: t("common.assistant"),
    icon: "M7.5 8.25h9m-9 3H12m-9.75 1.51c0 1.6 1.123 2.994 2.707 3.227 1.129.166 2.27.293 3.423.379.35.026.67.21.865.501L12 21l2.755-4.133a1.14 1.14 0 0 1 .865-.501 48.172 48.172 0 0 0 3.423-.379c1.584-.233 2.707-1.626 2.707-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0 0 12 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018Z",
  },
  {
    key: "settings",
    label: t("common.settings"),
    icon: "M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.325.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 0 1 1.37.49l1.296 2.247a1.125 1.125 0 0 1-.26 1.431l-1.003.827c-.293.241-.438.613-.43.992a7.723 7.723 0 0 1 0 .255c-.008.378.137.75.43.991l1.004.827c.424.35.534.955.26 1.43l-1.298 2.247a1.125 1.125 0 0 1-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.47 6.47 0 0 1-.22.128c-.331.183-.581.495-.644.869l-.213 1.281c-.09.543-.56.94-1.11.94h-2.594c-.55 0-1.019-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 0 1-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 0 1-1.369-.49l-1.297-2.247a1.125 1.125 0 0 1 .26-1.431l1.004-.827c.292-.24.437-.613.43-.991a6.932 6.932 0 0 1 0-.255c.007-.38-.138-.751-.43-.992l-1.004-.827a1.125 1.125 0 0 1-.26-1.43l1.297-2.247a1.125 1.125 0 0 1 1.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.086.22-.128.332-.183.582-.495.644-.869l.214-1.28Z M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z",
  },
]);

function handleFocusTask(taskId: number) {
  workspace.focusTask(taskId);
  mobileTab.value = "tasks";
}

function handleFocusEvent(eventId: number) {
  workspace.focusEvent(eventId);
  mobileTab.value = "calendar";
}

async function sendAndFocusAssistant(message: string) {
  mobileTab.value = "assistant";
  await workspace.sendAssistantMessage(message);
}

function toggleLocale() {
  const next = locale.value === "zh-CN" ? "en-US" : "zh-CN";
  workspace.setLocale(next);
}

function handleSettingsTabEnter() {
  void workspace.hydrateSettings();
}

function toggleSettingsView() {
  if (mobileTab.value === "settings") {
    mobileTab.value = "calendar";
    return;
  }
  mobileTab.value = "settings";
  handleSettingsTabEnter();
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
  <ErrorBoundary>
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
          <h2 class="text-base font-bold text-ink">{{ t("app.authorizationTitle") }}</h2>
          <p class="mt-1.5 text-sm text-ink-3">{{ t("app.authorizationDesc") }}</p>
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
            <span class="text-sm font-bold text-ink">{{ t("app.workspaceTitle") }}</span>
          </div>

          <div class="flex items-center gap-2">
            <span class="rounded-lg bg-surface-3 px-2.5 py-1 text-xs font-medium text-ink-2">
              <span class="font-semibold text-ink">{{ workspace.events.length }}</span> {{ t("common.calendar") }}
            </span>
            <span class="rounded-lg bg-surface-3 px-2.5 py-1 text-xs font-medium text-ink-2">
              <span class="font-semibold text-ink">{{ workspace.tasks.length }}</span> {{ t("common.tasks") }}
            </span>
            <button
              type="button"
              class="rounded-lg border border-border bg-white px-3 py-1.5 text-xs font-medium text-ink-2 transition hover:bg-surface-3"
              @click="toggleLocale"
            >
              {{ workspace.locale === "zh-CN" ? "EN" : "中" }}
            </button>
            <div class="mx-1 h-4 w-px bg-border" />
            <!-- Settings entry on desktop: toggles settings panel -->
            <button
              type="button"
              class="flex items-center gap-1.5 rounded-lg border border-border bg-white px-3 py-1.5 text-xs font-medium text-ink-2 transition hover:bg-surface-3"
              @click="toggleSettingsView()"
            >
              <svg class="h-3.5 w-3.5 text-ink-3" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.325.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 0 1 1.37.49l1.296 2.247a1.125 1.125 0 0 1-.26 1.431l-1.003.827c-.293.241-.438.613-.43.992a7.723 7.723 0 0 1 0 .255c-.008.378.137.75.43.991l1.004.827c.424.35.534.955.26 1.43l-1.298 2.247a1.125 1.125 0 0 1-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.47 6.47 0 0 1-.22.128c-.331.183-.581.495-.644.869l-.213 1.281c-.09.543-.56.94-1.11.94h-2.594c-.55 0-1.019-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 0 1-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 0 1-1.369-.49l-1.297-2.247a1.125 1.125 0 0 1 .26-1.431l1.004-.827c.292-.24.437-.613.43-.991a6.932 6.932 0 0 1 0-.255c.007-.38-.138-.751-.43-.992l-1.004-.827a1.125 1.125 0 0 1-.26-1.43l1.297-2.247a1.125 1.125 0 0 1 1.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.086.22-.128.332-.183.582-.495.644-.869l.214-1.28Z M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z" />
              </svg>
              {{ t("common.settings") }}
            </button>
          </div>
        </header>

        <!-- Main 2-col content -->
        <div class="flex min-h-0 flex-1 overflow-hidden">

          <!-- Left scrollable column: Calendar + Tasks or Settings -->
          <div class="flex-1 overflow-y-auto">
            <div class="mx-auto max-w-3xl space-y-4 px-6 py-5">
              <!-- Settings overlay on desktop -->
              <template v-if="mobileTab === 'settings'">
                <SettingsPanel
                  :profile="workspace.profile"
                  :saving-profile="workspace.savingProfile"
                  :google-calendar-status="workspace.googleCalendarStatus"
                  :google-calendar-sync-result="workspace.googleCalendarSyncResult"
                  :google-calendar-feedback="workspace.googleCalendarFeedback"
                  :starting-google-calendar-auth="workspace.startingGoogleCalendarAuth"
                  :syncing-google-calendar="workspace.syncingGoogleCalendar"
                  :weather-now="workspace.weatherNow"
                  :travel-estimate="workspace.travelEstimate"
                  :loading="workspace.loading"
                  @save-profile="workspace.saveProfile"
                  @connect-google-calendar="workspace.startGoogleCalendarAuth"
                  @sync-google-calendar="workspace.syncGoogleCalendar"
                  @dismiss-google-calendar-feedback="workspace.clearGoogleCalendarFeedback"
                />
              </template>
              <template v-else>
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
                <TasksPanel
                  :tasks="workspace.tasks"
                  :focused-task-id="workspace.focusedTaskId"
                  :loading="workspace.loading"
                  @send="sendAndFocusAssistant"
                  @delete-task="workspace.deleteTask"
                />
              </template>
            </div>
          </div>

          <!-- Right fixed Assistant column -->
          <div class="flex w-[400px] shrink-0 flex-col border-l border-border bg-white">
            <AssistantPanel
              :messages="workspace.messages"
              :sending="workspace.sending"
              :last-assistant-actions="workspace.lastAssistantActions"
              :assistant-proposals="workspace.assistantProposals"
              :assistant-signals="workspace.assistantSignals"
              :assistant-memory-candidates="workspace.assistantMemoryCandidates"
              :assistant-sessions="workspace.assistantSessions"
              :active-session-id="workspace.sessionId"
              :loading-proposals="workspace.loadingAssistantProposals"
              :loading-signals="workspace.loadingAssistantSignals"
              :loading-memory-candidates="workspace.loadingAssistantMemoryCandidates"
              :creating-session="workspace.creatingAssistantSession"
              :archiving-session="workspace.archivingAssistantSession"
              :clearing-session="workspace.clearingAssistantSession"
              :proposal-busy-id="workspace.proposalActionBusyId"
              :memory-candidate-busy-id="workspace.memoryCandidateBusyId"
              @send="workspace.sendAssistantMessage"
              @focus-task="handleFocusTask"
              @fetch-proposals="workspace.fetchAssistantProposals"
              @fetch-signals="workspace.fetchAssistantSignals"
              @fetch-memory-candidates="workspace.fetchAssistantMemoryCandidates"
              @confirm-proposal="workspace.confirmAssistantProposal"
              @reject-proposal="workspace.rejectAssistantProposal"
              @revise-proposal="workspace.reviseAssistantProposal"
              @retry-proposal="workspace.retryAssistantProposal"
              @confirm-memory-candidate="workspace.confirmAssistantMemoryCandidate"
              @reject-memory-candidate="workspace.rejectAssistantMemoryCandidate"
              @create-session="workspace.createAssistantSession"
              @switch-session="workspace.switchAssistantSession"
              @archive-session="workspace.archiveCurrentAssistantSession"
              @clear-session="workspace.clearCurrentAssistantSession"
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
            <span class="text-sm font-bold text-ink">{{ t("app.workspaceTitle") }}</span>
          </div>
          <div class="flex items-center gap-2">
            <button
              type="button"
              class="rounded-lg border border-border bg-white px-2 py-1 text-[10px] font-semibold text-ink-2 transition hover:bg-surface-3"
              @click="toggleLocale"
            >
              {{ workspace.locale === "zh-CN" ? "EN" : "中" }}
            </button>
          </div>
        </header>

        <!-- Tab content -->
        <div class="min-h-0 flex-1 overflow-y-auto bg-surface-2">
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

          <div v-else-if="mobileTab === 'tasks'" class="p-4">
            <TasksPanel
              :tasks="workspace.tasks"
              :focused-task-id="workspace.focusedTaskId"
              :loading="workspace.loading"
              @send="sendAndFocusAssistant"
              @delete-task="workspace.deleteTask"
            />
          </div>

          <!-- Assistant tab: fill full height via flex -->
          <div v-else-if="mobileTab === 'assistant'" class="flex h-full flex-col">
            <AssistantPanel
              :messages="workspace.messages"
              :sending="workspace.sending"
              :last-assistant-actions="workspace.lastAssistantActions"
              :assistant-proposals="workspace.assistantProposals"
              :assistant-signals="workspace.assistantSignals"
              :assistant-memory-candidates="workspace.assistantMemoryCandidates"
              :assistant-sessions="workspace.assistantSessions"
              :active-session-id="workspace.sessionId"
              :loading-proposals="workspace.loadingAssistantProposals"
              :loading-signals="workspace.loadingAssistantSignals"
              :loading-memory-candidates="workspace.loadingAssistantMemoryCandidates"
              :creating-session="workspace.creatingAssistantSession"
              :archiving-session="workspace.archivingAssistantSession"
              :clearing-session="workspace.clearingAssistantSession"
              :proposal-busy-id="workspace.proposalActionBusyId"
              :memory-candidate-busy-id="workspace.memoryCandidateBusyId"
              @send="workspace.sendAssistantMessage"
              @focus-task="handleFocusTask"
              @fetch-proposals="workspace.fetchAssistantProposals"
              @fetch-signals="workspace.fetchAssistantSignals"
              @fetch-memory-candidates="workspace.fetchAssistantMemoryCandidates"
              @confirm-proposal="workspace.confirmAssistantProposal"
              @reject-proposal="workspace.rejectAssistantProposal"
              @revise-proposal="workspace.reviseAssistantProposal"
              @retry-proposal="workspace.retryAssistantProposal"
              @confirm-memory-candidate="workspace.confirmAssistantMemoryCandidate"
              @reject-memory-candidate="workspace.rejectAssistantMemoryCandidate"
              @create-session="workspace.createAssistantSession"
              @switch-session="workspace.switchAssistantSession"
              @archive-session="workspace.archiveCurrentAssistantSession"
              @clear-session="workspace.clearCurrentAssistantSession"
            />
          </div>

          <div v-else-if="mobileTab === 'settings'" class="p-4">
            <SettingsPanel
              :profile="workspace.profile"
              :saving-profile="workspace.savingProfile"
              :google-calendar-status="workspace.googleCalendarStatus"
              :google-calendar-sync-result="workspace.googleCalendarSyncResult"
              :google-calendar-feedback="workspace.googleCalendarFeedback"
              :starting-google-calendar-auth="workspace.startingGoogleCalendarAuth"
              :syncing-google-calendar="workspace.syncingGoogleCalendar"
              :weather-now="workspace.weatherNow"
              :travel-estimate="workspace.travelEstimate"
              :loading="workspace.loading"
              @save-profile="workspace.saveProfile"
              @connect-google-calendar="workspace.startGoogleCalendarAuth"
              @sync-google-calendar="workspace.syncGoogleCalendar"
              @dismiss-google-calendar-feedback="workspace.clearGoogleCalendarFeedback"
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
            @click="mobileTab = tab.key as MobileTab; if (tab.key === 'settings') handleSettingsTabEnter()"
          >
            <span
              v-if="mobileTab === tab.key"
              class="absolute top-0 left-1/2 h-0.5 w-8 -translate-x-1/2 rounded-full bg-accent"
            />
            <svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke-width="1.8" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" :d="tab.icon" />
            </svg>
            {{ tab.label }}
          </button>
        </nav>

      </div>
    </div>
  </ErrorBoundary>
</template>
