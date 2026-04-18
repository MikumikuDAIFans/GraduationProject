import { defineStore } from "pinia";
import { api } from "@/api/client";
import { sendPlatformNotification } from "@/platform/notifications";
import { MobileNotificationService } from "@/plugins/capacitor";

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

export interface ToastItem {
  id: string;
  message: string;
  type: "info" | "success" | "warn" | "danger";
  createdAt: number;
}

export const useReminderStore = defineStore("reminder", {
  state: () => ({
    reminders: [] as Reminder[],
    toasts: [] as ToastItem[],
    seenReminderIds: [] as number[],
    initializedReminderSnapshot: false,
    socket: null as WebSocket | null,
    _cacheTimestamps: {} as Record<string, number>,
  }),
  actions: {
    isCacheValid(key: string): boolean {
      const timestamp = this._cacheTimestamps[key];
      if (!timestamp) return false;
      return Date.now() - timestamp < 15000;
    },

    invalidateCache(key: string) {
      delete this._cacheTimestamps[key];
    },

    async fetchReminders(force = false) {
      if (!force && this.isCacheValid("reminders")) return;
      try {
        const response = await api.get<Reminder[]>("/reminders");
        this.reminders = response.data;
        this._cacheTimestamps["reminders"] = Date.now();
      } catch (error) {
        console.error("Failed to fetch reminders:", error);
      }
    },

    pushToast(message: string, type: "info" | "success" | "warn" | "danger" = "info") {
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

    async notifyUser(title: string, message: string) {
      await sendPlatformNotification(title, message);
    },

    buildWebSocketUrl(path: string) {
      const fallbackBase = "http://127.0.0.1:8000/api";
      const base = typeof api.defaults.baseURL === "string" ? api.defaults.baseURL : fallbackBase;
      const httpUrl = new URL(base, typeof window !== "undefined" ? window.location.origin : undefined);
      const wsProtocol = httpUrl.protocol === "https:" ? "wss:" : "ws:";
      return `${wsProtocol}//${httpUrl.host}${path}`;
    },

    connectNotifications(onSnapshot: (payload: any) => void) {
      if (this.socket && this.socket.readyState <= WebSocket.OPEN) return;

      const socket = new WebSocket(this.buildWebSocketUrl("/ws/notifications?user_id=local-user"));
      socket.onerror = () => socket.close();
      socket.onmessage = (event) => {
        const payload = JSON.parse(event.data);
        if (payload.type === "workspace_snapshot") {
          onSnapshot(payload);
        }
      };
      socket.onclose = () => {
        this.socket = null;
        window.setTimeout(() => this.connectNotifications(onSnapshot), 3000);
      };
      this.socket = socket;
    },

    disconnectNotifications() {
      this.socket?.close();
      this.socket = null;
    },

    async registerMobileNotifications() {
      await MobileNotificationService.registerPushNotifications();
    },
  },
});
