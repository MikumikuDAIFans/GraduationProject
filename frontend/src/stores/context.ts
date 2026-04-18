import { defineStore } from "pinia";
import { api } from "@/api/client";

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

export const useContextStore = defineStore("context", {
  state: () => ({
    weatherLocation: "116.397,39.908",
    weatherNow: null as WeatherNow | null,
    travelOrigin: "Tiananmen, Beijing",
    travelDestination: "Peking University, Beijing",
    travelEstimate: null as TravelEstimate | null,
    _cacheTimestamps: {} as Record<string, number>,
  }),
  actions: {
    isCacheValid(key: string): boolean {
      const timestamp = this._cacheTimestamps[key];
      if (!timestamp) return false;
      return Date.now() - timestamp < 300000; // 5 minutes
    },

    invalidateCache(key: string) {
      delete this._cacheTimestamps[key];
    },

    async fetchWeatherNow(force = false) {
      if (!force && this.isCacheValid("weather")) return;
      try {
        const response = await api.get<WeatherNow>("/context/weather/now", {
          params: { location: this.weatherLocation },
        });
        this.weatherNow = response.data;
        this._cacheTimestamps["weather"] = Date.now();
      } catch (error) {
        console.error("Failed to fetch weather:", error);
      }
    },

    async fetchTravelEstimate(force = false) {
      if (!force && this.isCacheValid("travel")) return;
      try {
        const response = await api.get<TravelEstimate>("/context/travel", {
          params: {
            origin: this.travelOrigin,
            destination: this.travelDestination,
          },
        });
        this.travelEstimate = response.data;
        this._cacheTimestamps["travel"] = Date.now();
      } catch (error) {
        console.error("Failed to fetch travel estimate:", error);
      }
    },
  },
});
