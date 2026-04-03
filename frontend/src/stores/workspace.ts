import { defineStore } from "pinia";
import { api } from "@/api/client";
import { defaultInputAdapter } from "@/inputAdapters/textInput";
import { defaultOutputAdapter } from "@/outputAdapters/textOutput";
import { i18n, getSavedLocale, persistLocale, type SupportedLocale } from "@/i18n";
import { MobileNotificationService } from "@/plugins/capacitor";
import { sendPlatformNotification } from "@/platform/notifications";

export interface CalendarEvent {
  id: number;
  title: string;
  description?: string | null;
  start_time?: string | null;
  end_time?: string | null;
  location_name?: string | null;
  status?: string | null;
  source?: string | null;
  event_type?: string | null;
  linked_task_id?: number | null;
  departure_time?: string | null;
  travel_duration_minutes?: number | null;
  travel_mode?: string | null;
  external_event_id?: string | null;
  external_calendar_id?: string | null;
  external_etag?: string | null;
  sync_status?: string | null;
  last_synced_at?: string | null;
}

export interface Reminder {
  id: number;
  target_type: string;
  target_id: number;
  remind_type: string;
  remind_at: string;
  delivery_channel?: string | null;
  message?: string | null;
  status?: string | null;
}

export interface Suggestion {
  type: string;
  title: string;
  description: string;
  start_time: string;
  end_time: string;
  related_task_id?: number | null;
  related_event_id?: number | null;
  confidence?: number | null;
  split_group?: string | null;
  segment_index?: number | null;
  segment_total?: number | null;
  estimated_minutes?: number | null;
}

export interface AssistantAction {
  type: string;
  payload: Record<string, unknown>;
}

export interface AssistantInboxItem {
  id: string;
  kind: string;
  title: string;
  description: string;
  priority: number;
  thread_id?: string | null;
  read?: boolean;
  archived?: boolean;
  entry_count?: number | null;
  updated_at?: string | null;
  action_label?: string | null;
  action_message?: string | null;
  related_task_id?: number | null;
  related_event_id?: number | null;
  meta?: Record<string, unknown>;
}

export interface AssistantInbox {
  items: AssistantInboxItem[];
  total: number;
  unread_total: number;
}

export interface AssistantSummaryCard {
  id: string;
  title: string;
  value: string;
  description: string;
  tone: string;
  action_label?: string | null;
  action_message?: string | null;
  thread_id?: string | null;
  related_task_id?: number | null;
  related_event_id?: number | null;
  meta?: Record<string, unknown>;
}

export interface AssistantSummary {
  generated_at: string;
  unread_followups: number;
  cards: AssistantSummaryCard[];
}

export interface AssistantMessage {
  id: number | string;
  role: "user" | "assistant";
  content: string;
  tool_calls_json?: AssistantAction[] | null;
  created_at?: string;
}

export interface AssistantSession {
  id: number;
  user_id: string;
  session_type?: string | null;
  title: string;
  is_archived?: boolean;
  context_json?: Record<string, unknown> | null;
  created_at?: string | null;
  updated_at?: string | null;
  messages: AssistantMessage[];
}

export interface ToastItem {
  id: string;
  message: string;
  type: "info" | "warn" | "danger";
  createdAt: number;
}

export interface WeatherNow {
  location: string;
  obs_time?: string | null;
  temp?: string | null;
  feels_like?: string | null;
  text?: string | null;
  wind_dir?: string | null;
  wind_scale?: string | null;
  humidity?: string | null;
  precip?: string | null;
  vis?: string | null;
}

export interface TravelEstimate {
  origin: string;
  destination: string;
  origin_location: string;
  destination_location: string;
  mode: string;
  duration_seconds: number;
  duration_minutes: number;
  distance_meters: number;
  distance_km: number;
}

export interface UserProfile {
  id: number;
  username: string;
  display_name?: string | null;
  timezone: string;
  home_location_name?: string | null;
  home_location_coords?: string | null;
  work_location_name?: string | null;
  work_location_coords?: string | null;
  transport_preference?: string | null;
  wake_up_time?: string | null;
  sleep_time?: string | null;
  preferences_json?: Record<string, unknown> | null;
  google_calendar_status?: string;
  google_calendar_connected_at?: string | null;
  google_calendar_last_sync_at?: string | null;
  google_calendar_error?: string | null;
}

export interface TaskItem {
  id: number;
  user_id: string;
  content: string;
  description?: string | null;
  estimated_duration_minutes?: number | null;
  priority?: number | null;
  deadline?: string | null;
  status?: string | null;
  can_split?: boolean | null;
  preferred_period?: string | null;
  linked_event_id?: number | null;
  scheduled_minutes: number;
  scheduled_blocks_count: number;
  remaining_minutes?: number | null;
  completion_ratio?: number | null;
  completed_minutes: number;
  completed_blocks_count: number;
  execution_ratio?: number | null;
}

export interface GoogleCalendarStatus {
  enabled: boolean;
  status: string;
  connected: boolean;
  calendar_id: string;
  redirect_uri?: string | null;
  connected_at?: string | null;
  last_sync_at?: string | null;
  last_error?: string | null;
  has_refresh_token: boolean;
  auth_url?: string | null;
}

export interface GoogleCalendarSyncResult {
  status: string;
  pushed: number;
  imported: number;
  updated: number;
  skipped: number;
  deleted: number;
  last_sync_at?: string | null;
  details: string[];
}

export interface AIHealth {
  enabled: boolean;
  provider: string;
  circuit_open: boolean;
  circuit_open_until?: string | null;
  consecutive_failures: number;
}

export interface PerformancePath {
  path: string;
  count: number;
}

export interface PerformanceMetrics {
  uptime_seconds: number;
  request_count: number;
  last_request_ms: number;
  avg_request_ms: number;
  p95_request_ms: number;
  hottest_paths: PerformancePath[];
}

export interface FrontendPerformanceMetrics {
  first_paint_ms?: number | null;
  first_contentful_paint_ms?: number | null;
  largest_contentful_paint_ms?: number | null;
}

export const useWorkspaceStore = defineStore("workspace", {
  state: () => ({
    loading: false,
    sending: false,
    savingProfile: false,
    startingGoogleCalendarAuth: false,
    syncingGoogleCalendar: false,
    processingGoogleCalendarCallback: false,
    events: [] as CalendarEvent[],
    reminders: [] as Reminder[],
    tasks: [] as TaskItem[],
    todaySuggestions: [] as Suggestion[],
    nextSuggestions: [] as Suggestion[],
    sessionId: null as number | null,
    messages: [] as AssistantMessage[],
    lastAssistantActions: [] as AssistantAction[],
    assistantInbox: [] as AssistantInboxItem[],
    assistantInboxUnreadTotal: 0,
    assistantSummary: null as AssistantSummary | null,
    assistantSessions: [] as AssistantSession[],
    loadingAssistantSessions: false,
    creatingAssistantSession: false,
    archivingAssistantSession: false,
    clearingAssistantSession: false,
    weatherLocation: "116.397,39.908",
    weatherNow: null as WeatherNow | null,
    travelOrigin: "Tiananmen, Beijing",
    travelDestination: "Peking University, Beijing",
    travelEstimate: null as TravelEstimate | null,
    profile: null as UserProfile | null,
    googleCalendarStatus: null as GoogleCalendarStatus | null,
    googleCalendarSyncResult: null as GoogleCalendarSyncResult | null,
    googleCalendarFeedback: null as string | null,
    aiHealth: null as AIHealth | null,
    performanceMetrics: null as PerformanceMetrics | null,
    frontendPerformance: null as FrontendPerformanceMetrics | null,
    loadingPerformance: false,
    socket: null as WebSocket | null,
    toasts: [] as ToastItem[],
    seenReminderIds: [] as number[],
    initializedReminderSnapshot: false,
    focusedTaskId: null as number | null,
    focusedEventId: null as number | null,
    locale: getSavedLocale() as SupportedLocale,
    // 新增：缓存状态管理
    _cacheTimestamps: {} as Record<string, number>,
    _cacheDurations: {
      events: 30000,        // 30秒
      tasks: 30000,         // 30秒
      reminders: 15000,     // 15秒
      suggestions: 60000,   // 60秒
      weather: 300000,      // 5分钟
      travel: 300000,       // 5分钟
      profile: 60000,       // 1分钟
      performance: 30000,   // 30秒
      aiHealth: 30000,      // 30秒
      googleCalendar: 60000,// 1分钟
    },
    // 新增：请求防抖
    _pendingRequests: {} as Record<string, Promise<any>>,
  }),
  actions: {
    // 新增：缓存检查方法
    isCacheValid(key: string): boolean {
      const timestamp = this._cacheTimestamps[key];
      if (!timestamp) return false;
      const duration = this._cacheDurations[key as keyof typeof this._cacheDurations] || 30000;
      return Date.now() - timestamp < duration;
    },

    invalidateCache(key: string) {
      delete this._cacheTimestamps[key];
    },

    invalidateAllCache() {
      this._cacheTimestamps = {};
    },

    // 新增：带缓存的请求方法
    async cachedFetch<T>(key: string, fetchFn: () => Promise<T>): Promise<T | undefined> {
      // 如果缓存有效，跳过请求
      if (this.isCacheValid(key)) {
        return undefined; // 返回undefined表示使用了缓存
      }

      // 防止重复请求
      if (this._pendingRequests[key]) {
        return this._pendingRequests[key];
      }

      try {
        this._pendingRequests[key] = fetchFn();
        const result = await this._pendingRequests[key];
        this._cacheTimestamps[key] = Date.now();
        return result;
      } finally {
        delete this._pendingRequests[key];
      }
    },

    async hydrate() {
      this.loading = true;
      try {
        this.setLocale(this.locale);
        await this.fetchProfile();
        
        // 使用智能缓存，只获取过期或不存在的数据
        const fetchTasks = [];
        
        if (!this.isCacheValid('events')) fetchTasks.push(this.fetchEvents());
        if (!this.isCacheValid('tasks')) fetchTasks.push(this.fetchTasks());
        if (!this.isCacheValid('reminders')) fetchTasks.push(this.fetchReminders());
        if (!this.isCacheValid('suggestions')) fetchTasks.push(this.fetchSuggestions());
        if (!this.isCacheValid('googleCalendar')) fetchTasks.push(this.fetchGoogleCalendarStatus());
        
        // 总是获取最新的会话和摘要（用户交互相关）
        fetchTasks.push(
          this.fetchAssistantSessions(),
          this.fetchCurrentAssistantSession(),
          this.fetchAssistantSummary()
        );
        
        // 非关键数据，延迟加载
        setTimeout(async () => {
          await Promise.allSettled([
            !this.isCacheValid('weather') ? this.fetchWeatherNow() : Promise.resolve(),
            !this.isCacheValid('travel') ? this.fetchTravelEstimate() : Promise.resolve(),
            !this.isCacheValid('performance') ? this.fetchPerformanceSnapshot() : Promise.resolve(),
          ]);
        }, 1000);
        
        // 等待关键数据加载完成
        await Promise.allSettled(fetchTasks);
        
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
    async fetchEvents(force = false) {
      if (!force && this.isCacheValid('events')) return;
      try {
        const response = await api.get<CalendarEvent[]>("/events");
        this.events = response.data;
        this._cacheTimestamps['events'] = Date.now();
      } catch (error) {
        console.error("Failed to fetch events:", error);
      }
    },
    async fetchReminders(force = false) {
      if (!force && this.isCacheValid('reminders')) return;
      try {
        const response = await api.get<Reminder[]>("/reminders");
        this.reminders = response.data;
        this._cacheTimestamps['reminders'] = Date.now();
      } catch (error) {
        console.error("Failed to fetch reminders:", error);
      }
    },
    async fetchTasks(force = false) {
      if (!force && this.isCacheValid('tasks')) return;
      try {
        const response = await api.get<TaskItem[]>("/tasks");
        this.tasks = response.data;
        this._cacheTimestamps['tasks'] = Date.now();
      } catch (error) {
        console.error("Failed to fetch tasks:", error);
      }
    },
    async fetchSuggestions(force = false) {
      if (!force && this.isCacheValid('suggestions')) return;
      try {
        const [today, next] = await Promise.all([
          api.get<{ items: Suggestion[] }>("/suggestions/today"),
          api.get<{ items: Suggestion[] }>("/suggestions/next"),
        ]);
        this.todaySuggestions = today.data.items;
        this.nextSuggestions = next.data.items;
        this._cacheTimestamps['suggestions'] = Date.now();
      } catch (error) {
        console.error("Failed to fetch suggestions:", error);
      }
    },
    async fetchAssistantInbox() {
      try {
        const response = await api.get<AssistantInbox>("/assistant/inbox");
        this.assistantInbox = response.data.items;
        this.assistantInboxUnreadTotal = response.data.unread_total;
      } catch (error) {
        console.error("Failed to fetch assistant inbox:", error);
      }
    },
    async fetchAssistantSessions() {
      this.loadingAssistantSessions = true;
      try {
        const response = await api.get<{ items: AssistantSession[]; total: number }>("/assistant/sessions");
        this.assistantSessions = response.data.items;
      } finally {
        this.loadingAssistantSessions = false;
      }
    },
    async fetchCurrentAssistantSession() {
      try {
        const response = await api.get<{
          session: AssistantSession;
          inbox: AssistantInbox;
        }>("/assistant/current");
        this.sessionId = response.data.session.id;
        this.messages = response.data.session.messages;
        this.assistantInbox = response.data.inbox.items;
        this.assistantInboxUnreadTotal = response.data.inbox.unread_total;
        const existing = this.assistantSessions.find((item) => item.id === response.data.session.id);
        if (!existing) {
          this.assistantSessions = [response.data.session, ...this.assistantSessions];
        }
      } catch (error) {
        console.error("Failed to fetch current assistant session:", error);
      }
    },
    async fetchAssistantSummary() {
      try {
        const response = await api.get<AssistantSummary>("/assistant/summary");
        this.assistantSummary = response.data;
      } catch (error) {
        console.error("Failed to fetch assistant summary:", error);
      }
    },
    async fetchWeatherNow(force = false) {
      if (!force && this.isCacheValid('weather')) return;
      try {
        const response = await api.get<WeatherNow>("/context/weather/now", {
          params: { location: this.weatherLocation },
        });
        this.weatherNow = response.data;
        this._cacheTimestamps['weather'] = Date.now();
      } catch (error) {
        console.error("Failed to fetch weather:", error);
      }
    },
    async fetchTravelEstimate(force = false) {
      if (!force && this.isCacheValid('travel')) return;
      try {
        const response = await api.get<TravelEstimate>("/context/travel", {
          params: {
            origin: this.travelOrigin,
            destination: this.travelDestination,
          },
        });
        this.travelEstimate = response.data;
        this._cacheTimestamps['travel'] = Date.now();
      } catch (error) {
        console.error("Failed to fetch travel estimate:", error);
      }
    },
    async fetchProfile(force = false) {
      if (!force && this.isCacheValid('profile')) return;
      try {
        const response = await api.get<UserProfile>("/profile");
        this.profile = response.data;
        if (response.data.home_location_name) {
          this.travelOrigin = response.data.home_location_coords ?? response.data.home_location_name;
        }
        if (response.data.home_location_coords) {
          this.weatherLocation = response.data.home_location_coords;
        }
        if (response.data.work_location_name) {
          this.travelDestination = response.data.work_location_coords ?? response.data.work_location_name;
        }
        this._cacheTimestamps['profile'] = Date.now();
      } catch (error) {
        console.error("Failed to fetch profile:", error);
      }
    },
    async saveProfile(payload: Partial<UserProfile>) {
      this.savingProfile = true;
      try {
        const response = await api.put<UserProfile>("/profile", payload);
        this.profile = response.data;
        if (response.data.home_location_name) {
          this.travelOrigin = response.data.home_location_coords ?? response.data.home_location_name;
        }
        if (response.data.home_location_coords) {
          this.weatherLocation = response.data.home_location_coords;
        }
        if (response.data.work_location_name) {
          this.travelDestination = response.data.work_location_coords ?? response.data.work_location_name;
        }
        
        // 只使受影响的缓存失效
        this.invalidateCache('weather');
        this.invalidateCache('travel');
        this.invalidateCache('profile');
        
        // 异步获取更新后的数据
        Promise.allSettled([
          this.fetchWeatherNow(true),
          this.fetchTravelEstimate(true),
        ]);
        
        this.pushToast(
          this.locale === "zh-CN" ? "资料已保存" : "Profile saved",
          "success"
        );
      } catch (error) {
        console.error("Failed to save profile:", error);
        this.pushToast(
          this.locale === "zh-CN" ? "保存失败，请重试" : "Failed to save profile",
          "danger"
        );
      } finally {
        this.savingProfile = false;
      }
    },
    async fetchGoogleCalendarStatus() {
      try {
        const response = await api.get<GoogleCalendarStatus>("/google-calendar/status");
        this.googleCalendarStatus = response.data;
      } catch (error) {
        console.error("Failed to fetch Google Calendar status:", error);
      }
    },
    async fetchPerformanceSnapshot() {
      this.loadingPerformance = true;
      try {
        const [perf, ai] = await Promise.all([
          api.get<PerformanceMetrics>("/health/performance"),
          api.get<AIHealth>("/health/ai"),
        ]);
        this.performanceMetrics = perf.data;
        this.aiHealth = ai.data;
      } catch (error) {
        console.error("Failed to fetch performance snapshot:", error);
        // Silently degrade - performance metrics are non-critical
      } finally {
        this.loadingPerformance = false;
      }
    },
    captureFrontendPerformance() {
      if (typeof window === "undefined" || typeof performance === "undefined") {
        return;
      }

      const next: FrontendPerformanceMetrics = {};
      for (const entry of performance.getEntriesByType("paint")) {
        if (entry.name === "first-paint") {
          next.first_paint_ms = Math.round(entry.startTime);
        }
        if (entry.name === "first-contentful-paint") {
          next.first_contentful_paint_ms = Math.round(entry.startTime);
        }
      }

      if ("PerformanceObserver" in window) {
        try {
          const observer = new PerformanceObserver((list) => {
            for (const entry of list.getEntries()) {
              next.largest_contentful_paint_ms = Math.round(entry.startTime);
              this.frontendPerformance = { ...next };
            }
          });
          observer.observe({ type: "largest-contentful-paint", buffered: true });
          window.setTimeout(() => observer.disconnect(), 5000);
        } catch {
          // Ignore unsupported performance entry types.
        }
      }

      this.frontendPerformance = next;
    },
    async startGoogleCalendarAuth() {
      this.startingGoogleCalendarAuth = true;
      this.googleCalendarFeedback = null;
      try {
        const response = await api.get<{ auth_url: string }>("/google-calendar/auth/start");
        if (typeof window !== "undefined") {
          window.location.assign(response.data.auth_url);
        }
      } finally {
        this.startingGoogleCalendarAuth = false;
      }
    },
    async handleGoogleCalendarCallback() {
      if (typeof window === "undefined") {
        return;
      }

      this.processingGoogleCalendarCallback = true;
      try {
        const params = new URLSearchParams(window.location.search);
        const code = params.get("code");
        const state = params.get("state");
        const error = params.get("error");

        if (error) {
          this.googleCalendarFeedback = i18n.global.t("googleCalendar.authFailed", { error });
          return;
        }
        if (!code) {
          this.googleCalendarFeedback = i18n.global.t("googleCalendar.callbackMissingCode");
          return;
        }

        await api.get("/google-calendar/auth/callback", {
          params: { code, state },
        });
        this.googleCalendarFeedback = i18n.global.t("googleCalendar.connectedFeedback");
        await this.fetchGoogleCalendarStatus();
      } catch (error) {
        this.googleCalendarFeedback = this.extractApiError(error, i18n.global.t("googleCalendar.callbackFailed"));
      } finally {
        window.history.replaceState({}, "", "/");
        this.processingGoogleCalendarCallback = false;
      }
    },
    async syncGoogleCalendar() {
      this.syncingGoogleCalendar = true;
      this.googleCalendarFeedback = null;
      try {
        const response = await api.post<GoogleCalendarSyncResult>("/google-calendar/sync");
        this.googleCalendarSyncResult = response.data;
        this.googleCalendarFeedback = i18n.global.t("googleCalendar.syncFeedback", {
          pushed: response.data.pushed,
          imported: response.data.imported,
          updated: response.data.updated,
          skipped: response.data.skipped,
        });
        
        // 同步后使相关缓存失效
        this.invalidateCache('events');
        this.invalidateCache('tasks');
        this.invalidateCache('suggestions');
        this.invalidateCache('reminders');
        this.invalidateCache('googleCalendar');
        
        // 异步获取更新后的数据
        Promise.allSettled([
          this.fetchGoogleCalendarStatus(true),
          this.fetchEvents(true),
          this.fetchTasks(true),
          this.fetchSuggestions(true),
          this.fetchAssistantInbox(),
          this.fetchReminders(true),
        ]);
      } catch (error) {
        this.googleCalendarFeedback = this.extractApiError(error, i18n.global.t("googleCalendar.syncFailed"));
      } finally {
        this.syncingGoogleCalendar = false;
      }
    },
    clearGoogleCalendarFeedback() {
      this.googleCalendarFeedback = null;
    },
    async fetchSession(sessionId: number) {
      try {
        const response = await api.get<AssistantSession>(
          `/assistant/sessions/${sessionId}`,
        );
        this.sessionId = response.data.id;
        this.messages = response.data.messages;
        this.assistantSessions = this.assistantSessions.map((item) =>
          item.id === response.data.id ? response.data : item,
        );
      } catch (error) {
        console.error("Failed to fetch session:", error);
      }
    },
    async createAssistantSession(title?: string) {
      this.creatingAssistantSession = true;
      try {
        const response = await api.post<AssistantSession>("/assistant/sessions", { title });
        this.sessionId = response.data.id;
        this.messages = response.data.messages;
        this.assistantSessions = [response.data, ...this.assistantSessions.filter((item) => item.id !== response.data.id)];
        this.lastAssistantActions = [];
        this.pushToast(i18n.global.t("toast.sessionCreated"), "info");
      } catch (error) {
        this.pushToast(i18n.global.t("toast.sessionCreateFailed"), "danger");
        throw error;
      } finally {
        this.creatingAssistantSession = false;
      }
    },
    async switchAssistantSession(sessionId: number) {
      try {
        await this.fetchSession(sessionId);
      } catch (error) {
        this.pushToast(i18n.global.t("toast.sessionSwitchFailed"), "danger");
        throw error;
      }
    },
    async archiveCurrentAssistantSession() {
      if (this.sessionId == null) {
        return;
      }
      this.archivingAssistantSession = true;
      try {
        await api.post(`/assistant/sessions/${this.sessionId}/archive`);
        this.assistantSessions = this.assistantSessions.filter((item) => item.id !== this.sessionId);
        this.pushToast(i18n.global.t("toast.sessionArchived"), "info");
        await Promise.all([this.fetchAssistantSessions(), this.fetchCurrentAssistantSession()]);
      } catch (error) {
        this.pushToast(i18n.global.t("toast.sessionArchiveFailed"), "danger");
        throw error;
      } finally {
        this.archivingAssistantSession = false;
      }
    },
    async clearCurrentAssistantSession() {
      if (this.sessionId == null) {
        return;
      }
      this.clearingAssistantSession = true;
      try {
        await api.delete(`/assistant/sessions/${this.sessionId}/messages`);
        this.messages = [];
        this.lastAssistantActions = [];
        this.pushToast(i18n.global.t("toast.sessionCleared"), "info");
        await this.fetchAssistantSessions();
      } catch (error) {
        this.pushToast(i18n.global.t("toast.sessionClearFailed"), "danger");
        throw error;
      } finally {
        this.clearingAssistantSession = false;
      }
    },
    buildWebSocketUrl(path: string) {
      const fallbackBase = "http://127.0.0.1:8000/api";
      const base = typeof api.defaults.baseURL === "string" ? api.defaults.baseURL : fallbackBase;
      const httpUrl = new URL(base, typeof window !== "undefined" ? window.location.origin : undefined);
      const wsProtocol = httpUrl.protocol === "https:" ? "wss:" : "ws:";
      return `${wsProtocol}//${httpUrl.host}${path}`;
    },
    async refreshAssistantWorkspace(selective = true) {
      // selective模式只更新变化的数据
      if (selective) {
        await Promise.allSettled([
          this.fetchEvents(),
          this.fetchTasks(),
          this.fetchReminders(),
          this.fetchSuggestions(),
          this.fetchAssistantInbox(),
          this.fetchAssistantSummary(),
          this.sessionId != null ? this.fetchCurrentAssistantSession() : Promise.resolve(),
        ]);
      } else {
        // 完整刷新模式
        this.invalidateAllCache();
        await Promise.allSettled([
          this.fetchEvents(true),
          this.fetchTasks(true),
          this.fetchReminders(true),
          this.fetchSuggestions(true),
          this.fetchAssistantSessions(),
          this.fetchAssistantInbox(),
          this.fetchAssistantSummary(),
          this.fetchPerformanceSnapshot(),
          this.sessionId != null ? this.fetchSession(this.sessionId) : Promise.resolve(),
        ]);
      }
    },
    async sendAssistantMessageStream(message: string) {
      const parsedMessage = await defaultInputAdapter.parse(message);
      const normalizedMessage = parsedMessage.trim();
      if (!normalizedMessage) {
        return;
      }

      this.sending = true;
      const userMessageId = `local-${Date.now()}`;
      const assistantMsgId = `assistant-stream-${Date.now()}`;
      this.messages.push({
        id: userMessageId,
        role: "user",
        content: normalizedMessage,
      });
      this.messages.push({
        id: assistantMsgId,
        role: "assistant",
        content: "",
      });
      this.lastAssistantActions = [];

      let completed = false;
      try {
        await new Promise<void>((resolve, reject) => {
          let finished = false;
          const ws = new WebSocket(this.buildWebSocketUrl("/ws/assistant?user_id=local-user"));

          const rejectOnce = (error: unknown) => {
            if (finished) {
              return;
            }
            finished = true;
            try {
              ws.close();
            } catch {
              // ignore close errors
            }
            reject(error);
          };

          ws.onopen = () => {
            ws.send(JSON.stringify({ message: normalizedMessage, session_id: this.sessionId }));
          };

          ws.onmessage = (event) => {
            void (async () => {
              const data = JSON.parse(event.data) as {
                type: string;
                text?: string;
                actions?: AssistantAction[];
                session_id?: number;
                full_reply?: string;
              };
              const assistantMessage = this.messages.find((item) => item.id === assistantMsgId);

              if (data.type === "token") {
                if (assistantMessage) {
                  assistantMessage.content += data.text ?? "";
                }
                return;
              }

              if (data.type === "actions") {
                this.lastAssistantActions = data.actions ?? [];
                return;
              }

              if (data.type === "done") {
                finished = true;
                this.sessionId = data.session_id ?? this.sessionId;
                const rendered = await defaultOutputAdapter.render(data.full_reply ?? "");
                if (assistantMessage) {
                  assistantMessage.content = rendered;
                }
                ws.close();
                completed = true;
                this.sending = false;
                await this.refreshAssistantWorkspace();
                resolve();
                return;
              }

              if (data.type === "error") {
                rejectOnce(new Error(data.text || "Assistant WebSocket failed."));
              }
            })().catch(rejectOnce);
          };

          ws.onerror = () => {
            rejectOnce(new Error("Assistant WebSocket connection failed."));
          };

          ws.onclose = () => {
            if (!finished) {
              rejectOnce(new Error("Assistant WebSocket closed unexpectedly."));
            }
          };
        });
      } catch (error) {
        this.messages = this.messages.filter((item) => item.id !== userMessageId && item.id !== assistantMsgId);
        this.lastAssistantActions = [];
        this.sending = false;
        this.pushToast(this.extractApiError(error, i18n.global.t("toast.assistantFailed")), "danger");
        throw error;
      } finally {
        if (!completed) {
          this.sending = false;
        }
      }
    },
    async sendAssistantMessage(message: string) {
      const parsedMessage = await defaultInputAdapter.parse(message);
      const normalizedMessage = parsedMessage.trim();
      if (!normalizedMessage) {
        return;
      }

      try {
        await this.sendAssistantMessageStream(normalizedMessage);
        return;
      } catch {
        // Fallback to REST when WebSocket streaming is unavailable.
      }

      this.sending = true;
      this.messages.push({
        id: `local-${Date.now()}`,
        role: "user",
        content: normalizedMessage,
      });

      try {
        const response = await api.post<{
          session_id: number;
          reply: string;
          actions: AssistantAction[];
        }>("/assistant/message", {
          session_id: this.sessionId,
          message: normalizedMessage,
        });

        this.sessionId = response.data.session_id;
        const renderedReply = await defaultOutputAdapter.render(response.data.reply);
        this.messages.push({
          id: `assistant-${Date.now()}`,
          role: "assistant",
          content: renderedReply,
          tool_calls_json: response.data.actions,
        });
        this.lastAssistantActions = response.data.actions;

        await this.refreshAssistantWorkspace();
      } catch (error) {
        this.pushToast(this.extractApiError(error, i18n.global.t("toast.assistantFailed")), "danger");
        throw error;
      } finally {
        this.sending = false;
      }
    },
    async updateEventStatus(eventId: number, status: string) {
      try {
        await api.put(`/events/${eventId}`, { status });
        
        // 乐观更新本地状态
        const event = this.events.find(e => e.id === eventId);
        if (event) event.status = status;
        
        // 使相关缓存失效
        this.invalidateCache('events');
        this.invalidateCache('tasks');
        this.invalidateCache('reminders');
        this.invalidateCache('suggestions');
        
        // 异步获取更新后的数据
        Promise.allSettled([
          this.fetchEvents(true),
          this.fetchTasks(true),
          this.fetchReminders(true),
          this.fetchSuggestions(true),
          this.fetchAssistantSummary(),
        ]);
        
        this.pushToast(this.locale === "zh-CN" ? "状态已更新" : "Status updated", "success");
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
        await api.post("/assistant/inbox/" + itemId, null, { params: { action } });
        await this.fetchCurrentAssistantSession();
      } catch (error) {
        console.error("Failed to update inbox item:", error);
        // Show user-friendly error instead of crashing
        this.pushToast(i18n.global.t("toast.inboxUpdateFailed"), "danger");
      }
    },
    connectNotifications() {
      if (this.socket && this.socket.readyState <= WebSocket.OPEN) {
        return;
      }

      const socket = new WebSocket(this.buildWebSocketUrl("/ws/notifications?user_id=local-user"));
      socket.onerror = () => {
        socket.close();
      };
      socket.onmessage = (event) => {
        const payload = JSON.parse(event.data) as {
          type: string;
          reminders: Reminder[];
          today_suggestions: Suggestion[];
          next_suggestions: Suggestion[];
          assistant_inbox: AssistantInboxItem[];
          assistant_summary: AssistantSummary;
          events?: CalendarEvent[];
          tasks?: TaskItem[];
        };
        if (payload.type !== "workspace_snapshot") {
          return;
        }

        const previousIds = new Set(this.seenReminderIds);
        this.reminders = payload.reminders;
        this.todaySuggestions = payload.today_suggestions;
        this.nextSuggestions = payload.next_suggestions;
        this.assistantInbox = payload.assistant_inbox;
        this.assistantInboxUnreadTotal = payload.assistant_inbox.filter((item) => !item.read).length;
        this.assistantSummary = payload.assistant_summary;
        this.events = payload.events ?? this.events;
        this.tasks = payload.tasks ?? this.tasks;
        this.seenReminderIds = payload.reminders.map((item) => item.id);

        if (!this.initializedReminderSnapshot) {
          this.initializedReminderSnapshot = true;
          return;
        }

        for (const reminder of payload.reminders) {
          if (!previousIds.has(reminder.id) && reminder.status !== "read") {
            const message = reminder.message || reminder.remind_type;
            const toastType =
              reminder.remind_type === "conflict_warning"
                ? "danger"
                : reminder.remind_type === "departure" || reminder.remind_type === "task_deadline"
                  ? "warn"
                  : "info";
            this.pushToast(message, toastType);
            void this.notifyUser("Personal Affairs Assistant", message, reminder);
          }
        }
      };
      socket.onclose = () => {
        this.socket = null;
        window.setTimeout(() => {
          this.connectNotifications();
        }, 3000);
      };
      this.socket = socket;
    },
    disconnectNotifications() {
      this.socket?.close();
      this.socket = null;
    },
    async notifyUser(title: string, message: string, reminder?: Reminder) {
      void reminder;
      await sendPlatformNotification(title, message);
    },
    pushToast(message: string, type: "info" | "warn" | "danger" = "info") {
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
      this.toasts = this.toasts.filter((toast) => toast.id !== id);
    },
    extractApiError(error: unknown, fallback: string) {
      const maybeAxios = error as {
        response?: { data?: { detail?: string; error?: { message?: string } } | string };
        message?: string;
      };
      const detail = maybeAxios.response?.data;
      if (typeof detail === "string") {
        return detail;
      }
      if (detail && typeof detail === "object" && "detail" in detail && typeof detail.detail === "string") {
        return detail.detail;
      }
      if (detail && typeof detail === "object" && "error" in detail && typeof detail.error?.message === "string") {
        return detail.error.message;
      }
      return maybeAxios.message || fallback;
    },
    setLocale(locale: SupportedLocale) {
      this.locale = locale;
      i18n.global.locale.value = locale;
      persistLocale(locale);
    },
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
    async deleteTask(taskId: number) {
      try {
        await api.delete(`/tasks/${taskId}`);
        this.tasks = this.tasks.filter((t) => t.id !== taskId);
        if (this.focusedTaskId === taskId) this.focusedTaskId = null;
        
        // 使相关缓存失效
        this.invalidateCache('tasks');
        this.invalidateCache('suggestions');
        
        // 异步获取更新后的数据
        Promise.allSettled([
          this.fetchTasks(true),
          this.fetchSuggestions(true),
          this.fetchAssistantSummary(),
        ]);
        
        this.pushToast(
          this.locale === "zh-CN" ? "任务已删除" : "Task deleted",
          "success"
        );
      } catch (error) {
        console.error("Failed to delete task:", error);
        this.pushToast(
          this.locale === "zh-CN" ? "删除任务失败，请重试" : "Failed to delete task",
          "danger"
        );
      }
    },
    async deleteEvent(eventId: number) {
      try {
        await api.delete(`/events/${eventId}`);
        this.events = this.events.filter((e) => e.id !== eventId);
        if (this.focusedEventId === eventId) this.focusedEventId = null;
        
        // 使相关缓存失效
        this.invalidateCache('events');
        this.invalidateCache('tasks');
        this.invalidateCache('suggestions');
        
        // 异步获取更新后的数据
        Promise.allSettled([
          this.fetchEvents(true),
          this.fetchTasks(true),
          this.fetchSuggestions(true),
          this.fetchAssistantSummary(),
        ]);
        
        this.pushToast(
          this.locale === "zh-CN" ? "事件已删除" : "Event deleted",
          "success"
        );
      } catch (error) {
        console.error("Failed to delete event:", error);
        this.pushToast(
          this.locale === "zh-CN" ? "删除事件失败，请重试" : "Failed to delete event",
          "danger"
        );
      }
    },
  },
});
