import { defineStore } from "pinia";
import { api } from "@/api/client";
import { i18n } from "@/i18n";

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

export const useGoogleCalendarStore = defineStore("googleCalendar", {
  state: () => ({
    startingGoogleCalendarAuth: false,
    syncingGoogleCalendar: false,
    processingGoogleCalendarCallback: false,
    googleCalendarStatus: null as GoogleCalendarStatus | null,
    googleCalendarSyncResult: null as GoogleCalendarSyncResult | null,
    googleCalendarFeedback: null as string | null,
    _cacheTimestamps: {} as Record<string, number>,
  }),
  actions: {
    isCacheValid(key: string): boolean {
      const timestamp = this._cacheTimestamps[key];
      if (!timestamp) return false;
      return Date.now() - timestamp < 60000; // 1 minute
    },

    invalidateCache(key: string) {
      delete this._cacheTimestamps[key];
    },

    async fetchGoogleCalendarStatus(force = false) {
      if (!force && this.isCacheValid("googleCalendar")) return;
      try {
        const response = await api.get<GoogleCalendarStatus>("/google-calendar/status");
        this.googleCalendarStatus = response.data;
        this._cacheTimestamps["googleCalendar"] = Date.now();
      } catch (error) {
        console.error("Failed to fetch Google Calendar status:", error);
      }
    },

    async startGoogleCalendarAuth() {
      this.startingGoogleCalendarAuth = true;
      this.googleCalendarFeedback = null;
      try {
        const response = await api.get<{ auth_url: string }>("/google-calendar/auth/start");
        window.location.href = response.data.auth_url;
      } catch (error) {
        console.error("Failed to start Google Calendar auth:", error);
      } finally {
        this.startingGoogleCalendarAuth = false;
      }
    },

    async handleGoogleCalendarCallback() {
      if (typeof window === "undefined") return;
      this.processingGoogleCalendarCallback = true;
      this.googleCalendarFeedback = null;
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
        await this.fetchGoogleCalendarStatus(true);
      } catch (error: any) {
        this.googleCalendarFeedback = error.response?.data?.detail || i18n.global.t("googleCalendar.callbackFailed");
      } finally {
        window.history.replaceState({}, "", "/");
        this.processingGoogleCalendarCallback = false;
      }
    },

    async syncGoogleCalendar() {
      this.syncingGoogleCalendar = true;
      this.googleCalendarFeedback = null;
      try {
        const response = await api.post("/google-calendar/sync");
        this.googleCalendarSyncResult = response.data;
        this.googleCalendarFeedback = "Sync completed";
        this.invalidateCache("googleCalendar");
      } catch (error: any) {
        this.googleCalendarFeedback = error.response?.data?.detail || "Sync failed";
      } finally {
        this.syncingGoogleCalendar = false;
      }
    },
  },
});
