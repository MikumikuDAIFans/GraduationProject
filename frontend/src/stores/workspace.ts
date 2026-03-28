import { defineStore } from "pinia";
import { api } from "@/api/client";

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
    weatherLocation: "116.397,39.908",
    weatherNow: null as WeatherNow | null,
    travelOrigin: "Tiananmen, Beijing",
    travelDestination: "Peking University, Beijing",
    travelEstimate: null as TravelEstimate | null,
    profile: null as UserProfile | null,
    googleCalendarStatus: null as GoogleCalendarStatus | null,
    googleCalendarSyncResult: null as GoogleCalendarSyncResult | null,
    googleCalendarFeedback: null as string | null,
    socket: null as WebSocket | null,
    seenReminderIds: [] as number[],
    focusedTaskId: null as number | null,
    focusedEventId: null as number | null,
  }),
  actions: {
    async hydrate() {
      this.loading = true;
      try {
        await this.fetchProfile();
        await Promise.all([
          this.fetchEvents(),
          this.fetchTasks(),
          this.fetchReminders(),
          this.fetchSuggestions(),
          this.fetchCurrentAssistantSession(),
          this.fetchAssistantSummary(),
          this.fetchWeatherNow(),
          this.fetchTravelEstimate(),
          this.fetchGoogleCalendarStatus(),
        ]);
        this.connectNotifications();
      } finally {
        this.loading = false;
      }
    },
    async fetchEvents() {
      const response = await api.get<CalendarEvent[]>("/events");
      this.events = response.data;
    },
    async fetchReminders() {
      const response = await api.get<Reminder[]>("/reminders");
      this.reminders = response.data;
    },
    async fetchTasks() {
      const response = await api.get<TaskItem[]>("/tasks");
      this.tasks = response.data;
    },
    async fetchSuggestions() {
      const [today, next] = await Promise.all([
        api.get<{ items: Suggestion[] }>("/suggestions/today"),
        api.get<{ items: Suggestion[] }>("/suggestions/next"),
      ]);
      this.todaySuggestions = today.data.items;
      this.nextSuggestions = next.data.items;
    },
    async fetchAssistantInbox() {
      const response = await api.get<AssistantInbox>("/assistant/inbox");
      this.assistantInbox = response.data.items;
      this.assistantInboxUnreadTotal = response.data.unread_total;
    },
    async fetchCurrentAssistantSession() {
      const response = await api.get<{
        session: { id: number; messages: AssistantMessage[] };
        inbox: AssistantInbox;
      }>("/assistant/current");
      this.sessionId = response.data.session.id;
      this.messages = response.data.session.messages;
      this.assistantInbox = response.data.inbox.items;
      this.assistantInboxUnreadTotal = response.data.inbox.unread_total;
    },
    async fetchAssistantSummary() {
      const response = await api.get<AssistantSummary>("/assistant/summary");
      this.assistantSummary = response.data;
    },
    async fetchWeatherNow() {
      const response = await api.get<WeatherNow>("/context/weather/now", {
        params: { location: this.weatherLocation },
      });
      this.weatherNow = response.data;
    },
    async fetchTravelEstimate() {
      const response = await api.get<TravelEstimate>("/context/travel", {
        params: {
          origin: this.travelOrigin,
          destination: this.travelDestination,
        },
      });
      this.travelEstimate = response.data;
    },
    async fetchProfile() {
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
        await Promise.all([this.fetchWeatherNow(), this.fetchTravelEstimate()]);
      } finally {
        this.savingProfile = false;
      }
    },
    async fetchGoogleCalendarStatus() {
      const response = await api.get<GoogleCalendarStatus>("/google-calendar/status");
      this.googleCalendarStatus = response.data;
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
          this.googleCalendarFeedback = `Google Calendar authorization failed: ${error}`;
          return;
        }
        if (!code) {
          this.googleCalendarFeedback = "Google Calendar callback did not include an authorization code.";
          return;
        }

        await api.get("/google-calendar/auth/callback", {
          params: { code, state },
        });
        this.googleCalendarFeedback = "Google Calendar connected. You can sync local events now.";
        await this.fetchGoogleCalendarStatus();
      } catch (error) {
        this.googleCalendarFeedback = this.extractApiError(error, "Google Calendar callback failed.");
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
        this.googleCalendarFeedback = [
          `Pushed ${response.data.pushed} local event(s)`,
          `imported ${response.data.imported}`,
          `updated ${response.data.updated}`,
          `skipped ${response.data.skipped}`,
        ].join(", ");
        await Promise.all([
          this.fetchGoogleCalendarStatus(),
          this.fetchEvents(),
          this.fetchTasks(),
          this.fetchSuggestions(),
          this.fetchAssistantInbox(),
          this.fetchReminders(),
        ]);
      } catch (error) {
        this.googleCalendarFeedback = this.extractApiError(error, "Google Calendar sync failed.");
      } finally {
        this.syncingGoogleCalendar = false;
      }
    },
    clearGoogleCalendarFeedback() {
      this.googleCalendarFeedback = null;
    },
    async fetchSession(sessionId: number) {
      const response = await api.get<{ id: number; messages: AssistantMessage[] }>(
        `/assistant/sessions/${sessionId}`,
      );
      this.sessionId = response.data.id;
      this.messages = response.data.messages;
    },
    async sendAssistantMessage(message: string) {
      if (!message.trim()) {
        return;
      }

      this.sending = true;
      this.messages.push({
        id: `local-${Date.now()}`,
        role: "user",
        content: message,
      });

      try {
        const response = await api.post<{
          session_id: number;
          reply: string;
          actions: AssistantAction[];
        }>("/assistant/message", {
          session_id: this.sessionId,
          message,
        });

        this.sessionId = response.data.session_id;
        this.messages.push({
          id: `assistant-${Date.now()}`,
          role: "assistant",
          content: response.data.reply,
          tool_calls_json: response.data.actions,
        });
        this.lastAssistantActions = response.data.actions;

        await Promise.all([
          this.fetchEvents(),
          this.fetchTasks(),
          this.fetchReminders(),
          this.fetchSuggestions(),
          this.fetchAssistantInbox(),
          this.fetchAssistantSummary(),
          this.fetchSession(this.sessionId),
        ]);
      } finally {
        this.sending = false;
      }
    },
    async updateEventStatus(eventId: number, status: string) {
      await api.put(`/events/${eventId}`, { status });
      await Promise.all([
        this.fetchEvents(),
        this.fetchTasks(),
        this.fetchReminders(),
        this.fetchSuggestions(),
        this.fetchCurrentAssistantSession(),
        this.fetchAssistantSummary(),
      ]);
    },
    async updateInboxItem(itemId: string, action: "read" | "archive") {
      await api.post("/assistant/inbox/" + itemId, null, { params: { action } });
      await this.fetchCurrentAssistantSession();
    },
    connectNotifications() {
      if (this.socket && this.socket.readyState <= WebSocket.OPEN) {
        return;
      }

      const socket = new WebSocket("ws://127.0.0.1:8000/ws/notifications?user_id=local-user");
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
        this.seenReminderIds = payload.reminders.map((item) => item.id);

        for (const reminder of payload.reminders) {
          if (!previousIds.has(reminder.id) && reminder.status !== "read") {
            this.notifyBrowser(reminder.message || reminder.remind_type);
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
    notifyBrowser(message: string) {
      if (typeof window === "undefined" || !("Notification" in window)) {
        return;
      }
      if (Notification.permission === "granted") {
        new Notification("Personal Affairs Assistant", { body: message });
      }
    },
    extractApiError(error: unknown, fallback: string) {
      const maybeAxios = error as {
        response?: { data?: { detail?: string } | string };
        message?: string;
      };
      const detail = maybeAxios.response?.data;
      if (typeof detail === "string") {
        return detail;
      }
      if (detail && typeof detail === "object" && "detail" in detail && typeof detail.detail === "string") {
        return detail.detail;
      }
      return maybeAxios.message || fallback;
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
      await api.delete(`/tasks/${taskId}`);
      this.tasks = this.tasks.filter((t) => t.id !== taskId);
      if (this.focusedTaskId === taskId) this.focusedTaskId = null;
      await Promise.all([this.fetchSuggestions(), this.fetchAssistantSummary()]);
    },
    async deleteEvent(eventId: number) {
      await api.delete(`/events/${eventId}`);
      this.events = this.events.filter((e) => e.id !== eventId);
      if (this.focusedEventId === eventId) this.focusedEventId = null;
      await Promise.all([this.fetchTasks(), this.fetchSuggestions(), this.fetchAssistantSummary()]);
    },
  },
});
