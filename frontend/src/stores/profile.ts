import { defineStore } from "pinia";
import { api } from "@/api/client";
import { i18n, getSavedLocale, persistLocale, type SupportedLocale } from "@/i18n";

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

export const useProfileStore = defineStore("profile", {
  state: () => ({
    profile: null as UserProfile | null,
    savingProfile: false,
    locale: getSavedLocale() as SupportedLocale,
    _cacheTimestamps: {} as Record<string, number>,
  }),
  actions: {
    isCacheValid(key: string): boolean {
      const timestamp = this._cacheTimestamps[key];
      if (!timestamp) return false;
      return Date.now() - timestamp < 60000;
    },

    invalidateCache(key: string) {
      delete this._cacheTimestamps[key];
    },

    async fetchProfile(force = false) {
      if (!force && this.isCacheValid("profile")) return;
      try {
        const response = await api.get<UserProfile>("/profile");
        this.profile = response.data;
        this._cacheTimestamps["profile"] = Date.now();
      } catch (error) {
        console.error("Failed to fetch profile:", error);
      }
    },

    async saveProfile(payload: Partial<UserProfile>) {
      this.savingProfile = true;
      try {
        const response = await api.put<UserProfile>("/profile", payload);
        this.profile = response.data;
        this.invalidateCache("profile");
      } catch (error) {
        console.error("Failed to save profile:", error);
        throw error;
      } finally {
        this.savingProfile = false;
      }
    },

    setLocale(locale: SupportedLocale) {
      this.locale = locale;
      i18n.global.locale.value = locale;
      persistLocale(locale);
    },
  },
});
