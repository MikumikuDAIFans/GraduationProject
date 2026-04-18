import { defineStore } from "pinia";
import { api } from "@/api/client";

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

export const useSystemStore = defineStore("system", {
  state: () => ({
    aiHealth: {
      enabled: false,
      provider: "gemini",
      circuit_open: false,
      circuit_open_until: null,
      consecutive_failures: 0,
    } as AIHealth,
    backendPerformance: {
      uptime_seconds: 0,
      request_count: 0,
      last_request_ms: 0,
      avg_request_ms: 0,
      p95_request_ms: 0,
      hottest_paths: [],
    } as PerformanceMetrics,
    frontendPerformance: {
      first_paint_ms: null,
      first_contentful_paint_ms: null,
      largest_contentful_paint_ms: null,
    } as FrontendPerformanceMetrics,
    loadingPerformance: false,
    _cacheTimestamps: {} as Record<string, number>,
  }),
  actions: {
    isCacheValid(key: string): boolean {
      const timestamp = this._cacheTimestamps[key];
      if (!timestamp) return false;
      return Date.now() - timestamp < 120000; // 2 minutes
    },

    invalidateCache(key: string) {
      delete this._cacheTimestamps[key];
    },

    captureFrontendMetrics() {
      const navigation = performance.getEntriesByType?.("navigation")?.[0] as PerformanceNavigationTiming | undefined;
      if (navigation) {
        this.frontendPerformance.first_paint_ms = Math.round(navigation.domContentLoadedEventEnd - navigation.startTime);
        this.frontendPerformance.first_contentful_paint_ms = Math.round(navigation.loadEventEnd - navigation.startTime);
        this.frontendPerformance.largest_contentful_paint_ms = Math.round(navigation.loadEventEnd - navigation.startTime);
      }
    },

    async fetchAIHealth(force = false) {
      if (!force && this.isCacheValid("ai_health")) return;
      try {
        const response = await api.get<AIHealth>("/health/ai");
        this.aiHealth = response.data;
        this._cacheTimestamps["ai_health"] = Date.now();
      } catch (error) {
        console.error("Failed to fetch AI health:", error);
      }
    },

    async fetchBackendPerformance(force = false) {
      if (!force && this.isCacheValid("backend_perf")) return;
      this.loadingPerformance = true;
      try {
        const response = await api.get<PerformanceMetrics>("/health/performance");
        this.backendPerformance = response.data;
        this._cacheTimestamps["backend_perf"] = Date.now();
      } catch (error) {
        console.error("Failed to fetch backend performance:", error);
      } finally {
        this.loadingPerformance = false;
      }
    },
  },
});
