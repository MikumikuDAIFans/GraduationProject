/**
 * Workspace Store — Thin Compatibility Facade
 * 
 * This store now delegates to the new focused stores created during P2-2 refactoring:
 * - useEventsStore: CalendarEvent, TaskItem, CRUD operations
 * - useAssistantStore: Sessions, messages, WebSocket streaming
 * - useReminderStore: WebSocket notifications, toasts
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
  AssistantMemoryCandidate,
  AssistantMemoryFileSummary,
  AssistantMemoryRead,
  AssistantMessage,
  AssistantProposal,
  AssistantProposalOption,
  AssistantSession,
} from "@/stores/assistant";
export type { ToastItem } from "@/stores/reminder";
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
    assistantProposals: () => useAssistantStore().assistantProposals,
    assistantMemoryCandidates: () => useAssistantStore().assistantMemoryCandidates,
    assistantMemory: () => useAssistantStore().assistantMemory,
    assistantSessions: () => useAssistantStore().assistantSessions,
    loadingAssistantSessions: () => useAssistantStore().loadingAssistantSessions,
    loadingAssistantProposals: () => useAssistantStore().loadingAssistantProposals,
    loadingAssistantMemoryCandidates: () => useAssistantStore().loadingAssistantMemoryCandidates,
    creatingAssistantSession: () => useAssistantStore().creatingAssistantSession,
    archivingAssistantSession: () => useAssistantStore().archivingAssistantSession,
    clearingAssistantSession: () => useAssistantStore().clearingAssistantSession,
    proposalActionBusyId: () => useAssistantStore().proposalActionBusyId,
    memoryCandidateBusyId: () => useAssistantStore().memoryCandidateBusyId,

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
      const profileStore = useProfileStore();

      this.loading = true;
      try {
        this.setLocale(this.locale);
        await profileStore.fetchProfile();
        this.syncProfileContext();

        // Layer A: critical first-screen data only
        await Promise.allSettled([
          eventsStore.fetchEvents(),
          eventsStore.fetchTasks(),
          assistantStore.fetchCurrentAssistantSession(),
          assistantStore.fetchAssistantSessions(),
        ]);

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

    // Layer B: settings-page data (Google Calendar status + context)
    async hydrateSettings() {
      const gcStore = useGoogleCalendarStore();
      const contextStore = useContextStore();
      const profileStore = useProfileStore();
      this.syncProfileContext();
      await Promise.allSettled([
        gcStore.fetchGoogleCalendarStatus(),
        profileStore.fetchProfile(),
      ]);
      this.syncProfileContext();
      await Promise.allSettled([
        contextStore.fetchWeatherNow(),
        contextStore.fetchTravelEstimate(),
      ]);
    },

    // Delegate to focused stores
    async fetchEvents(force = false) { return useEventsStore().fetchEvents(force); },
    async fetchTasks(force = false) { return useEventsStore().fetchTasks(force); },
    async fetchAssistantSessions() { return useAssistantStore().fetchAssistantSessions(); },
    async fetchAssistantProposals() { return useAssistantStore().fetchAssistantProposals(); },
    async fetchAssistantMemoryCandidates() { return useAssistantStore().fetchAssistantMemoryCandidates(); },
    async fetchAssistantMemory() { return useAssistantStore().fetchAssistantMemory(); },
    async fetchCurrentAssistantSession() { return useAssistantStore().fetchCurrentAssistantSession(); },
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
    async confirmAssistantProposal(proposalId: number, optionId: string) {
      const assistantStore = useAssistantStore();
      const eventsStore = useEventsStore();
      try {
        const proposal = await assistantStore.confirmAssistantProposal(proposalId, optionId);
        this.pushToast(this.locale === "zh-CN" ? "方案已执行" : "Proposal executed", "success");
        await Promise.allSettled([
          eventsStore.fetchEvents(true),
          eventsStore.fetchTasks(true),
        ]);
        return proposal;
      } catch (error) {
        console.error("Failed to confirm proposal:", error);
        this.pushToast(
          this.locale === "zh-CN" ? "执行方案失败，请重试" : "Failed to execute proposal",
          "danger"
        );
        throw error;
      }
    },
    async rejectAssistantProposal(proposalId: number) {
      try {
        const proposal = await useAssistantStore().rejectAssistantProposal(proposalId);
        this.pushToast(this.locale === "zh-CN" ? "已拒绝方案" : "Proposal rejected", "info");
        return proposal;
      } catch (error) {
        console.error("Failed to reject proposal:", error);
        this.pushToast(
          this.locale === "zh-CN" ? "拒绝方案失败，请重试" : "Failed to reject proposal",
          "danger"
        );
        throw error;
      }
    },
    async reviseAssistantProposal(proposalId: number, message: string) {
      try {
        const proposal = await useAssistantStore().reviseAssistantProposal(proposalId, message);
        this.pushToast(this.locale === "zh-CN" ? "已提交修改" : "Revision submitted", "success");
        return proposal;
      } catch (error) {
        console.error("Failed to revise proposal:", error);
        this.pushToast(
          this.locale === "zh-CN" ? "修改方案失败，请重试" : "Failed to revise proposal",
          "danger"
        );
        throw error;
      }
    },
    async retryAssistantProposal(proposalId: number) {
      const assistantStore = useAssistantStore();
      const eventsStore = useEventsStore();
      try {
        const proposal = await assistantStore.retryAssistantProposal(proposalId);
        this.pushToast(this.locale === "zh-CN" ? "已重新执行方案" : "Proposal retried", "success");
        await Promise.allSettled([
          eventsStore.fetchEvents(true),
          eventsStore.fetchTasks(true),
        ]);
        return proposal;
      } catch (error) {
        console.error("Failed to retry proposal:", error);
        this.pushToast(
          this.locale === "zh-CN" ? "重试方案失败，请重试" : "Failed to retry proposal",
          "danger"
        );
        throw error;
      }
    },
    async confirmAssistantMemoryCandidate(candidateId: number) {
      try {
        const candidate = await useAssistantStore().confirmAssistantMemoryCandidate(candidateId);
        this.pushToast(this.locale === "zh-CN" ? "记忆已写入" : "Memory saved", "success");
        return candidate;
      } catch (error) {
        console.error("Failed to confirm memory candidate:", error);
        this.pushToast(
          this.locale === "zh-CN" ? "写入记忆失败，请重试" : "Failed to save memory",
          "danger"
        );
        throw error;
      }
    },
    async rejectAssistantMemoryCandidate(candidateId: number) {
      try {
        const candidate = await useAssistantStore().rejectAssistantMemoryCandidate(candidateId);
        this.pushToast(this.locale === "zh-CN" ? "已拒绝记忆" : "Memory rejected", "info");
        return candidate;
      } catch (error) {
        console.error("Failed to reject memory candidate:", error);
        this.pushToast(
          this.locale === "zh-CN" ? "拒绝记忆失败，请重试" : "Failed to reject memory",
          "danger"
        );
        throw error;
      }
    },
    async sendAssistantMessageStream(message: string) {
      return useAssistantStore().sendAssistantMessageStream(
        message,
        () => this.refreshAssistantAfterSend(),
      );
    },
    async sendAssistantMessage(message: string) {
      return useAssistantStore().sendAssistantMessage(
        message,
        () => this.refreshAssistantAfterSend(),
      );
    },
    async refreshAssistantAfterSend() {
      const assistantStore = useAssistantStore();
      const eventsStore = useEventsStore();
      const reminderStore = useReminderStore();
      await Promise.allSettled([
        assistantStore.fetchAssistantSessions(),
        assistantStore.fetchAssistantProposals(),
        assistantStore.fetchAssistantMemoryCandidates(),
      ]);

      const notificationSocket = reminderStore.socket;
      const websocketOpen =
        typeof WebSocket !== "undefined" &&
        notificationSocket?.readyState === WebSocket.OPEN;
      if (!websocketOpen) {
        await Promise.allSettled([
          eventsStore.fetchEvents(true),
          eventsStore.fetchTasks(true),
        ]);
      }
    },
    async refreshAssistantWorkspace(selective = true) {
      const eventsStore = useEventsStore();
      const assistantStore = useAssistantStore();

      if (selective) {
        await Promise.allSettled([
          eventsStore.fetchEvents(),
          eventsStore.fetchTasks(),
          assistantStore.fetchCurrentAssistantSession(),
          assistantStore.fetchAssistantProposals(),
          assistantStore.fetchAssistantMemoryCandidates(),
        ]);
      } else {
        await Promise.allSettled([
          eventsStore.fetchEvents(true),
          eventsStore.fetchTasks(true),
          assistantStore.fetchAssistantSessions(),
        ]);
      }
    },
    async updateEventStatus(eventId: number, status: string) {
      const eventsStore = useEventsStore();

      try {
        await eventsStore.updateEventStatus(eventId, status);
        this.pushToast(this.locale === "zh-CN" ? "状态已更新" : "Status updated", "success");
        // Refresh related data
        await Promise.allSettled([
          eventsStore.fetchEvents(true),
          eventsStore.fetchTasks(true),
        ]);
      } catch (error) {
        console.error("Failed to update event status:", error);
        this.pushToast(
          this.locale === "zh-CN" ? "更新状态失败，请重试" : "Failed to update status",
          "danger"
        );
      }
    },
    async deleteTask(taskId: number) {
      const eventsStore = useEventsStore();

      try {
        await eventsStore.deleteTask(taskId);
        if (this.focusedTaskId === taskId) this.focusedTaskId = null;
        this.pushToast(this.locale === "zh-CN" ? "任务已删除" : "Task deleted", "success");
        await eventsStore.fetchTasks(true);
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

      try {
        // Pass skipRefresh=true to avoid double-fetching, since eventsStore.deleteEvent already refreshes
        await eventsStore.deleteEvent(eventId, true);
        if (this.focusedEventId === eventId) this.focusedEventId = null;
        this.pushToast(this.locale === "zh-CN" ? "事件已删除" : "Event deleted", "success");
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

