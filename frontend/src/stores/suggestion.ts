import { defineStore } from "pinia";
import { api } from "@/api/client";

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

export const useSuggestionStore = defineStore("suggestion", {
  state: () => ({
    todaySuggestions: [] as Suggestion[],
    nextSuggestions: [] as Suggestion[],
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

    async fetchSuggestions(force = false) {
      if (!force && this.isCacheValid("suggestions")) return;
      try {
        const [today, next] = await Promise.all([
          api.get<{ items: Suggestion[] }>("/suggestions/today"),
          api.get<{ items: Suggestion[] }>("/suggestions/next"),
        ]);
        this.todaySuggestions = today.data.items;
        this.nextSuggestions = next.data.items;
        this._cacheTimestamps["suggestions"] = Date.now();
      } catch (error) {
        console.error("Failed to fetch suggestions:", error);
      }
    },
  },
});
