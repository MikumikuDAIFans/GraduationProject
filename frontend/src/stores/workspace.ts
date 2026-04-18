/**
 * Workspace Store — Thin Compatibility Facade
 * 
 * This store now delegates to the new focused stores created during P2-2 refactoring:
 * - useEventsStore: CalendarEvent, TaskItem, CRUD operations
 * - useAssistantStore: Sessions, messages, WebSocket streaming, inbox/summary
 * - useReminderStore: Reminders, suggestions, WebSocket notifications, toasts
 * - useProfileStore: UserProfile, locale management
 * - useContextStore: Weather, travel estimates
 * - useGoogleCalendarStore: Google Calendar auth/sync
 * - useSystemStore: AI health, performance metrics
 * 
 * All existing component imports remain valid. New code should import from the focused stores directly.
 */
import { defineStore } from "pinia";
import { api } from "@/api/client";
import { i18n, getSavedLocale, persistLocale, type SupportedLocale } from "@/i18n";
import { MobileNotificationService } from "@/plugins/capacitor";
import { sendPlatformNotification } from "@/platform/notifications";

// Re-export all types for backward compatibility
export type { CalendarEvent, TaskItem } from "@/stores/events";
export type {
  AssistantAction,
  AssistantInboxItem,
  AssistantInbox,
  AssistantSummaryCard,
  AssistantSummary,
  AssistantMessage,
  AssistantSession,
} from "@/stores/assistant";
export type { Reminder, Suggestion, ToastItem } from "@/stores/reminder";
export type { UserProfile } from "@/stores/profile";
export type { WeatherNow, TravelEstimate } from "@/stores/context";
export type { GoogleCalendarStatus, GoogleCalendarSyncResult } from "@/stores/googleCalendar";
export type {
  AIHealth,
  PerformanceMetrics,
  PerformancePath,
  FrontendPerformanceMetrics,
} from "@/stores/system";

// Import focused stores
import { useEventsStore } from "@/stores/events";
import { useAssistantStore } from "@/stores/assistant";
import { useReminderStore } from "@/stores/reminder";
import { useSuggestionStore } from "@/stores/suggestion";
import { useProfileStore } from "@/stores/profile";
import { useContextStore } from "@/stores/context";
import { useGoogleCalendarStore } from "@/stores/googleCalendar";
import { useSystemStore } from "@/stores/system";

/**
 * Thin compatibility facade that mirrors the original workspace store API
 * by delegating to the new focused stores.
 */
export const useWorkspaceStore = defineStore("workspace", {
  state: () => ({
    // Loading states (delegated to respective stores)
    loading: false,
    sending: false,
    // Focus states (remain here — cross-cutting concern)
    focusedTaskId: null as number | null,
    focusedEventId: null as number | null,
    // Locale (remains here for bootstrap simplicity)
    locale: getSavedLocale() as SupportedLocale,
    // Toast proxy (delegated to reminder store)
    toasts: [] as import("@/stores/reminder").ToastItem[],
  }),
  getters: {
    // Event/Task proxies
    events: () => useEventsStore().events,
    tasks: () => useEventsStore().tasks,

    // Assistant proxies
    sessionId: () => useAssistantStore().sessionId,
    messages: () => useAssistantStore().messages,
    lastAssistantActions: () => useAssistantStore().lastAssistantActions,
    assistantInbox: () => useAssistantStore().assistantInbox,
    assistantInboxUnreadTotal: () => useAssistantStore().assistantInboxUnreadTotal,
    assistantSummary: () => useAssistantStore().assistantSummary,
    assistantSessions: () => useAssistantStore().assistantSessions,
    loadingAssistantSessions: () => useAssistantStore().loadingAssistantSessions,
    creatingAssistantSession: () => useAssistantStore().creatingAssistantSession,
    archivingAssistantSession: () => useAssistantStore().archivingAssistantSession,
    clearingAssistantSession: () => useAssistantStore().clearingAssistantSession,

    // Reminder/Suggestion proxies
    reminders: () => useReminderStore().reminders,
    todaySuggestions: () => useSuggestionStore().todaySuggestions,
    nextSuggestions: () => useSuggestionStore().nextSuggestions,
    seenReminderIds: () => useReminderStore().seenReminderIds,
    initializedReminderSnapshot: () => useReminderStore().initializedReminderSnapshot,

    // Profile proxy
    profile: () => useProfileStore().profile,
    savingProfile: () => useProfileStore().savingProfile,

    // Context proxies
    weatherLocation: () => useContextStore().weatherLocation,
    weatherNow: () => useContextStore().weatherNow,
    travelOrigin: () => useContextStore().travelOrigin,
    travelDestination: () => useContextStore().travelDestination,
    travelEstimate: () => useContextStore().travelEstimate,

    // Google Calendar proxies
    startingGoogleCalendarAuth: () => useGoogleCalendarStore().startingGoogleCalendarAuth,
    syncingGoogleCalendar: () => useGoogleCalendarStore().syncingGoogleCalendar,
    processingGoogleCalendarCallback: () => useGoogleCalendarStore().processingGoogleCalendarCallback,
    googleCalendarStatus: () => useGoogleCalendarStore().googleCalendarStatus,
    googleCalendarSyncResult: () => useGoogleCalendarStore().googleCalendarSyncResult,
    googleCalendarFeedback: () => useGoogleCalendarStore().googleCalendarFeedback,

    // System proxies
    aiHealth: () => useSystemStore().aiHealth,
    performanceMetrics: () => useSystemStore().backendPerformance,
    frontendPerformance: () => useSystemStore().frontendPerformance,
    loadingPerformance: () => useSystemStore().loadingPerformance,
  },
  actions: {
    syncProfileContext() {
      const profile = useProfileStore().profile;
      if (!profile) return;

      const contextStore = useContextStore();
      if (profile.home_location_name) {
        contextStore.travelOrigin = profile.home_location_coords ?? profile.home_location_name;
      }
      if (profile.home_location_coords) {
        contextStore.weatherLocation = profile.home_location_coords;
      }
      if (profile.work_location_name) {
        contextStore.travelDestination = profile.work_location_coords ?? profile.work_location_name;
      }
    },

    // Hydration orchestrator — coordinates all stores
    async hydrate() {
      const eventsStore = useEventsStore();
      const assistantStore = useAssistantStore();
      const reminderStore = useReminderStore();
      const suggestionStore = useSuggestionStore();
      const profileStore = useProfileStore();
      const contextStore = useContextStore();
      const gcStore = useGoogleCalendarStore();
      const systemStore = useSystemStore();

      this.loading = true;
      try {
        this.setLocale(this.locale);
        await profileStore.fetchProfile();
        this.syncProfileContext();

        // Fetch critical data in parallel
        await Promise.allSettled([
          eventsStore.fetchEvents(),
          eventsStore.fetchTasks(),
          reminderStore.fetchReminders(),
          suggestionStore.fetchSuggestions(),
          gcStore.fetchGoogleCalendarStatus(),
          assistantStore.fetchAssistantSessions(),
          assistantStore.fetchCurrentAssistantSession(),
          assistantStore.fetchAssistantSummary(),
        ]);

        // Non-critical data, delayed load
        setTimeout(async () => {
          await Promise.allSettled([
            contextStore.fetchWeatherNow(),
            contextStore.fetchTravelEstimate(),
            systemStore.fetchBackendPerformance(),
            systemStore.fetchAIHealth(),
          ]);
        }, 1000);

        this.captureFrontendPerformance();
        await MobileNotificationService.registerPushNotifications();
        this.connectNotifications();
      } catch (error) {
        console.error("Hydration failed:", error);
        this.pushToast(
          this.locale === "zh-CN" ? "加载失败，请刷新页面" : "Failed to load",
          "danger"
        );
      } finally {
        this.loading = false;
      }
    },

    // Delegate to focused stores
    async fetchEvents(force = false) { return useEventsStore().fetchEvents(force); },
    async fetchTasks(force = false) { return useEventsStore().fetchTasks(force); },
    async fetchReminders(force = false) { return useReminderStore().fetchReminders(force); },
    async fetchSuggestions(force = false) { return useSuggestionStore().fetchSuggestions(force); },
    async fetchAssistantInbox() { return useAssistantStore().fetchAssistantInbox(); },
    async fetchAssistantSessions() { return useAssistantStore().fetchAssistantSessions(); },
    async fetchCurrentAssistantSession() { return useAssistantStore().fetchCurrentAssistantSession(); },
    async fetchAssistantSummary() { return useAssistantStore().fetchAssistantSummary(); },
    async fetchWeatherNow(force = false) { return useContextStore().fetchWeatherNow(force); },
    async fetchTravelEstimate(force = false) { return useContextStore().fetchTravelEstimate(force); },
    async fetchProfile(force = false) {
      await useProfileStore().fetchProfile(force);
      this.syncProfileContext();
    },
    async saveProfile(payload: Partial<import("@/stores/profile").UserProfile>) {
      await useProfileStore().saveProfile(payload);
      this.syncProfileContext();
      const contextStore = useContextStore();
      await Promise.allSettled([
        contextStore.fetchWeatherNow(true),
        contextStore.fetchTravelEstimate(true),
      ]);
    },
    async fetchGoogleCalendarStatus() { return useGoogleCalendarStore().fetchGoogleCalendarStatus(); },
    async fetchPerformanceSnapshot() { return useSystemStore().fetchBackendPerformance(); },
    async startGoogleCalendarAuth() { return useGoogleCalendarStore().startGoogleCalendarAuth(); },
    async handleGoogleCalendarCallback() { return useGoogleCalendarStore().handleGoogleCalendarCallback(); },
    async syncGoogleCalendar() { return useGoogleCalendarStore().syncGoogleCalendar(); },
    clearGoogleCalendarFeedback() { useGoogleCalendarStore().googleCalendarFeedback = null; },
    async fetchSession(sessionId: number) { return useAssistantStore().fetchSession(sessionId); },
    async createAssistantSession(title?: string) { return useAssistantStore().createAssistantSession(title); },
    async switchAssistantSession(sessionId: number) { return useAssistantStore().switchAssistantSession(sessionId); },
    async archiveCurrentAssistantSession() { return useAssistantStore().archiveCurrentAssistantSession(); },
    async clearCurrentAssistantSession() { return useAssistantStore().clearCurrentAssistantSession(); },
    async sendAssistantMessageStream(message: string) { return useAssistantStore().sendAssistantMessageStream(message); },
    async sendAssistantMessage(message: string) { return useAssistantStore().sendAssistantMessage(message); },
    async refreshAssistantWorkspace(selective = true) {
      const eventsStore = useEventsStore();
      const reminderStore = useReminderStore();
      const suggestionStore = useSuggestionStore();
      const assistantStore = useAssistantStore();

      if (selective) {
        await Promise.allSettled([
          eventsStore.fetchEvents(),
          eventsStore.fetchTasks(),
          reminderStore.fetchReminders(),
          suggestionStore.fetchSuggestions(),
          assistantStore.fetchAssistantInbox(),
          assistantStore.fetchAssistantSummary(),
          assistantStore.fetchCurrentAssistantSession(),
        ]);
      } else {
        await Promise.allSettled([
          eventsStore.fetchEvents(true),
          eventsStore.fetchTasks(true),
          reminderStore.fetchReminders(true),
          suggestionStore.fetchSuggestions(true),
          assistantStore.fetchAssistantSessions(),
          assistantStore.fetchAssistantInbox(),
          assistantStore.fetchAssistantSummary(),
          useSystemStore().fetchBackendPerformance(),
          this.sessionId != null ? assistantStore.fetchSession(this.sessionId) : Promise.resolve(),
        ]);
      }
    },
    async updateEventStatus(eventId: number, status: string) {
      const eventsStore = useEventsStore();
      const reminderStore = useReminderStore();
      const suggestionStore = useSuggestionStore();
      const assistantStore = useAssistantStore();

      try {
        await eventsStore.updateEventStatus(eventId, status);
        this.pushToast(this.locale === "zh-CN" ? "状态已更新" : "Status updated", "success");
        // Refresh related data
        await Promise.allSettled([
          eventsStore.fetchEvents(true),
          eventsStore.fetchTasks(true),
          reminderStore.fetchReminders(true),
          suggestionStore.fetchSuggestions(true),
          assistantStore.fetchAssistantSummary(),
        ]);
      } catch (error) {
        console.error("Failed to update event status:", error);
        this.pushToast(
          this.locale === "zh-CN" ? "更新状态失败，请重试" : "Failed to update status",
          "danger"
        );
      }
    },
    async updateInboxItem(itemId: string, action: "read" | "archive") {
      try {
        await useAssistantStore().updateInboxItem(itemId, action);
      } catch (error) {
        console.error("Failed to update inbox item:", error);
        this.pushToast("Inbox update failed", "danger");
      }
    },
    async deleteTask(taskId: number) {
      const eventsStore = useEventsStore();
      const suggestionStore = useSuggestionStore();
      const assistantStore = useAssistantStore();

      try {
        await eventsStore.deleteTask(taskId);
        if (this.focusedTaskId === taskId) this.focusedTaskId = null;
        this.pushToast(this.locale === "zh-CN" ? "任务已删除" : "Task deleted", "success");
        await Promise.allSettled([
          eventsStore.fetchTasks(true),
          suggestionStore.fetchSuggestions(true),
          assistantStore.fetchAssistantSummary(),
        ]);
      } catch (error) {
        console.error("Failed to delete task:", error);
        this.pushToast(
          this.locale === "zh-CN" ? "删除任务失败，请重试" : "Failed to delete task",
          "danger"
        );
      }
    },
    async deleteEvent(eventId: number) {
      const eventsStore = useEventsStore();
      const suggestionStore = useSuggestionStore();
      const assistantStore = useAssistantStore();

      try {
        // Pass skipRefresh=true to avoid double-fetching, since eventsStore.deleteEvent already refreshes
        await eventsStore.deleteEvent(eventId, true);
        if (this.focusedEventId === eventId) this.focusedEventId = null;
        this.pushToast(this.locale === "zh-CN" ? "事件已删除" : "Event deleted", "success");
        // Only refresh suggestions and summary, events are already refreshed in eventsStore.deleteEvent
        await Promise.allSettled([
          suggestionStore.fetchSuggestions(true),
          assistantStore.fetchAssistantSummary(),
        ]);
      } catch (error) {
        console.error("Failed to delete event:", error);
        this.pushToast(
          this.locale === "zh-CN" ? "删除事件失败，请重试" : "Failed to delete event",
          "danger"
        );
      }
    },

    // WebSocket notification connection (remains here — cross-cutting)
    connectNotifications() {
      const reminderStore = useReminderStore();
      const eventsStore = useEventsStore();
      reminderStore.connectNotifications((payload) => {
        // Sync events/tasks from WebSocket snapshot, but filter out recently deleted events
        if (payload.events) {
          const filteredEvents = (payload.events as any[]).filter(
            (e) => !eventsStore._recentlyDeletedEventIds.includes(e.id)
          );
          eventsStore.$patch({ events: filteredEvents });
        }
        if (payload.tasks) eventsStore.$patch({ tasks: payload.tasks });
      });
    },
    disconnectNotifications() {
      useReminderStore().disconnectNotifications();
    },
    async notifyUser(title: string, message: string, reminder?: import("@/stores/reminder").Reminder) {
      void reminder;
      await sendPlatformNotification(title, message);
    },

    // Toast system (proxied to reminder store)
    pushToast(message: string, type: "info" | "success" | "warn" | "danger" = "info") {
      useReminderStore().pushToast(message, type);
      // Keep local copy for backward compat
      this.toasts.push({
        id: `toast-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
        message,
        type,
        createdAt: Date.now(),
      });
      if (this.toasts.length > 5) {
        this.toasts = this.toasts.slice(-5);
      }
    },
    dismissToast(id: string) {
      useReminderStore().dismissToast(id);
      this.toasts = this.toasts.filter((toast) => toast.id !== id);
    },

    // Focus management (remains here — cross-cutting concern)
    focusTask(taskId: number | null) {
      this.focusedTaskId = taskId;
      this.focusedEventId = null;
    },
    focusEvent(eventId: number | null) {
      this.focusedEventId = eventId;
      this.focusedTaskId = null;
    },
    clearFocus() {
      this.focusedTaskId = null;
      this.focusedEventId = null;
    },

    // Locale management
    setLocale(locale: SupportedLocale) {
      this.locale = locale;
      i18n.global.locale.value = locale;
      persistLocale(locale);
      useProfileStore().$patch({ locale });
    },

    // Error extraction utility
    extractApiError(error: unknown, fallback: string) {
      const maybeAxios = error as {
        response?: { data?: { detail?: string; error?: { message?: string } } | string };
        message?: string;
      };
      const detail = maybeAxios.response?.data;
      if (typeof detail === "string") return detail;
      if (detail && typeof detail === "object" && "detail" in detail && typeof detail.detail === "string") {
        return detail.detail;
      }
      if (detail && typeof detail === "object" && "error" in detail && typeof detail.error?.message === "string") {
        return detail.error.message;
      }
      return maybeAxios.message || fallback;
    },

    // Performance capture (remains here — frontend-only)
    captureFrontendPerformance() {
      const systemStore = useSystemStore();
      systemStore.captureFrontendMetrics();
    },

    buildWebSocketUrl(path: string) {
      const fallbackBase = "http://127.0.0.1:8000/api";
      const base = typeof api.defaults.baseURL === "string" ? api.defaults.baseURL : fallbackBase;
      const httpUrl = new URL(base, typeof window !== "undefined" ? window.location.origin : undefined);
      const wsProtocol = httpUrl.protocol === "https:" ? "wss:" : "ws:";
      return `${wsProtocol}//${httpUrl.host}${path}`;
    },
  },
});

