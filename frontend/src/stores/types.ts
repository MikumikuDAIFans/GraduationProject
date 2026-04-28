/**
 * Shared type exports for all stores.
 * Components can import types from this single file to stay backwards-compatible.
 */
export type { CalendarEvent, TaskItem } from "@/stores/events";
export type {
  AssistantAction,
  AssistantMessage,
  AssistantSession,
} from "@/stores/assistant";
export type { ToastItem } from "@/stores/reminder";
export type { UserProfile } from "@/stores/profile";
export type {
  WeatherNow,
  TravelEstimate,
} from "@/stores/context";
export type {
  GoogleCalendarStatus,
  GoogleCalendarSyncResult,
} from "@/stores/googleCalendar";
export type {
  AIHealth,
  PerformanceMetrics,
  PerformancePath,
  FrontendPerformanceMetrics,
} from "@/stores/system";
