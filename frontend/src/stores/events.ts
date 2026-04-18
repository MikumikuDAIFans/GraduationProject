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

export const useEventsStore = defineStore("events", {
  state: () => ({
    events: [] as CalendarEvent[],
    tasks: [] as TaskItem[],
    focusedTaskId: null as number | null,
    focusedEventId: null as number | null,
    _cacheTimestamps: {} as Record<string, number>,
    _cacheDurations: {
      events: 30000,
      tasks: 30000,
    },
    _recentlyDeletedEventIds: [] as number[],
  }),
  actions: {
    isCacheValid(key: string): boolean {
      const timestamp = this._cacheTimestamps[key];
      if (!timestamp) return false;
      const duration = this._cacheDurations[key as keyof typeof this._cacheDurations] || 30000;
      return Date.now() - timestamp < duration;
    },

    invalidateCache(key: string) {
      delete this._cacheTimestamps[key];
    },

    async fetchEvents(force = false) {
      if (!force && this.isCacheValid("events")) return;
      try {
        const response = await api.get<CalendarEvent[]>("/events");
        this.events = response.data;
        this._cacheTimestamps["events"] = Date.now();
      } catch (error) {
        console.error("Failed to fetch events:", error);
      }
    },

    async fetchTasks(force = false) {
      if (!force && this.isCacheValid("tasks")) return;
      try {
        const response = await api.get<TaskItem[]>("/tasks");
        this.tasks = response.data;
        this._cacheTimestamps["tasks"] = Date.now();
      } catch (error) {
        console.error("Failed to fetch tasks:", error);
      }
    },

    async updateEventStatus(eventId: number, status: string) {
      try {
        await api.put(`/events/${eventId}`, { status });
        const event = this.events.find((e) => e.id === eventId);
        if (event) event.status = status;
        this.invalidateCache("events");
        this.invalidateCache("tasks");
        await Promise.allSettled([this.fetchEvents(true), this.fetchTasks(true)]);
      } catch (error) {
        console.error("Failed to update event status:", error);
        throw error;
      }
    },

    async deleteEvent(eventId: number, skipRefresh = false) {
      try {
        await api.delete(`/events/${eventId}`);
        this.events = this.events.filter((e) => e.id !== eventId);
        if (this.focusedEventId === eventId) this.focusedEventId = null;
        // Track recently deleted event to prevent WebSocket from resurrecting it
        this._recentlyDeletedEventIds.push(eventId);
        setTimeout(() => {
          this._recentlyDeletedEventIds = this._recentlyDeletedEventIds.filter((id) => id !== eventId);
        }, 10000);
        this.invalidateCache("events");
        this.invalidateCache("tasks");
        if (!skipRefresh) {
          await Promise.allSettled([this.fetchEvents(true), this.fetchTasks(true)]);
        }
      } catch (error) {
        console.error("Failed to delete event:", error);
        throw error;
      }
    },

    async deleteTask(taskId: number) {
      try {
        await api.delete(`/tasks/${taskId}`);
        this.tasks = this.tasks.filter((t) => t.id !== taskId);
        if (this.focusedTaskId === taskId) this.focusedTaskId = null;
        this.invalidateCache("tasks");
        await Promise.allSettled([this.fetchTasks(true)]);
      } catch (error) {
        console.error("Failed to delete task:", error);
        throw error;
      }
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
  },
});
