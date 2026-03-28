<script setup lang="ts">
import FullCalendar from "@fullcalendar/vue3";
import dayGridPlugin from "@fullcalendar/daygrid";
import timeGridPlugin from "@fullcalendar/timegrid";
import interactionPlugin from "@fullcalendar/interaction";
import { computed, ref, watch } from "vue";
import type { CalendarEvent, TaskItem } from "@/stores/workspace";

const props = defineProps<{
  events: CalendarEvent[];
  tasks: TaskItem[];
  loading: boolean;
  focusedEventId?: number | null;
  focusedTaskId?: number | null;
  mobile?: boolean;
}>();

const emit = defineEmits<{
  "update-status": [eventId: number, status: string];
  "send-assistant": [message: string];
  "delete-event": [eventId: number];
}>();

const focusedCardRef = ref<HTMLElement | null>(null);

watch(
  () => [props.focusedEventId, props.focusedTaskId],
  () => {
    if (props.focusedEventId != null || props.focusedTaskId != null) {
      requestAnimationFrame(() => {
        focusedCardRef.value?.scrollIntoView({ behavior: "smooth", block: "center" });
      });
    }
  },
);

const calendarEvents = computed(() =>
  props.events.map((event) => ({
    id: String(event.id),
    title: event.source === "google_imported" ? `☁ ${event.title}` : event.title,
    start: event.start_time ?? undefined,
    end: event.end_time ?? undefined,
    classNames: [
      event.source === "google_imported" ? "event-google" : "event-local",
      event.event_type === "focus_block" ? "event-focus-block" : "",
    ],
  })),
);

const departureGuides = computed(() =>
  props.events.filter((event) => event.departure_time && event.travel_duration_minutes),
);

const highlightedEvents = computed(() =>
  [...props.events]
    .filter((e) => e.start_time || e.source === "google_imported")
    .sort((a, b) => (b.start_time ?? "").localeCompare(a.start_time ?? ""))
    .slice(0, 8),
);

const taskMap = computed(() => new Map(props.tasks.map((t) => [t.id, t])));

function linkedTask(event: CalendarEvent) {
  if (!event.linked_task_id) return null;
  return taskMap.value.get(event.linked_task_id) ?? null;
}

function canResolveFocusBlock(event: CalendarEvent) {
  return event.event_type === "focus_block" && event.status !== "completed" && event.status !== "canceled";
}

function isEventFocused(event: CalendarEvent) {
  if (props.focusedEventId != null && event.id === props.focusedEventId) return true;
  if (props.focusedTaskId != null && event.linked_task_id === props.focusedTaskId) return true;
  return false;
}

function askAssistantAboutTask(event: CalendarEvent) {
  const task = linkedTask(event);
  if (!task) return;
  emit("send-assistant", `现在进展如何，接下来怎么安排任务"${task.content}"`);
}

function syncBadge(status?: string | null) {
  if (status === "synced") return { label: "Synced", cls: "bg-positive-light text-positive" };
  if (status === "sync_error") return { label: "Error", cls: "bg-danger-light text-danger" };
  if (status === "imported") return { label: "Imported", cls: "bg-sky-50 text-sky-600" };
  return { label: "Local", cls: "bg-slate-100 text-slate-500" };
}
</script>

<template>
  <section class="rounded-2xl border border-white/70 bg-white/70 shadow-panel backdrop-blur-xl">
    <!-- Header -->
    <div class="flex items-center justify-between gap-3 px-5 py-4">
      <div>
        <p class="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">Calendar</p>
        <h2 class="mt-0.5 text-lg font-bold text-ink">Workspace Timeline</h2>
      </div>
      <div class="flex items-center gap-2">
        <span v-if="loading" class="rounded-xl bg-warn-light px-3 py-1 text-xs font-semibold text-warn">Syncing…</span>
        <span v-else class="rounded-xl bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-500">{{ events.length }} events</span>
      </div>
    </div>

    <!-- FullCalendar -->
    <div class="border-t border-slate-100 px-4 pb-4 pt-3">
      <FullCalendar
        class="calendar-shell"
        :options="{
          plugins: [dayGridPlugin, timeGridPlugin, interactionPlugin],
          initialView: mobile ? 'timeGridDay' : 'timeGridWeek',
          headerToolbar: mobile
            ? { left: 'prev,next', center: 'title', right: 'today' }
            : { left: 'prev,next today', center: 'title', right: 'dayGridMonth,timeGridWeek,timeGridDay' },
          events: calendarEvents,
          height: 'auto',
          nowIndicator: true,
        }"
      />
    </div>

    <!-- Legend -->
    <div class="flex flex-wrap gap-2 border-t border-slate-100 px-5 py-3">
      <span class="rounded-lg bg-indigo-50 px-2.5 py-1 text-[11px] font-semibold text-accent">● Local</span>
      <span class="rounded-lg bg-sky-50 px-2.5 py-1 text-[11px] font-semibold text-sky-600">☁ Google imported</span>
      <span class="rounded-lg bg-positive-light px-2.5 py-1 text-[11px] font-semibold text-positive">✓ Mirror synced</span>
      <span class="rounded-lg bg-danger-light px-2.5 py-1 text-[11px] font-semibold text-danger">⚠ Sync error</span>
    </div>

    <!-- Event list -->
    <div v-if="highlightedEvents.length" class="border-t border-slate-100 px-5 py-4">
      <p class="mb-3 text-xs font-semibold uppercase tracking-[0.22em] text-slate-400">Recent Events</p>
      <div class="space-y-2">
        <div
          v-for="event in highlightedEvents"
          :key="`evt-${event.id}`"
          :ref="(el) => { if (isEventFocused(event)) focusedCardRef = el as HTMLElement; }"
          class="flex flex-wrap items-start gap-3 rounded-xl border px-4 py-3 transition-all duration-200"
          :class="isEventFocused(event)
            ? 'border-accent/30 bg-accent-light ring-2 ring-accent/20 shadow-sm'
            : 'border-slate-100 bg-white/80 hover:border-slate-200'"
        >
          <!-- Left: title + meta -->
          <div class="min-w-0 flex-1">
            <div class="flex flex-wrap items-center gap-2">
              <p class="text-sm font-semibold text-ink">{{ event.title }}</p>
              <span
                class="rounded-md px-1.5 py-0.5 text-[10px] font-bold"
                :class="syncBadge(event.sync_status).cls"
              >
                {{ syncBadge(event.sync_status).label }}
              </span>
              <span v-if="event.event_type === 'focus_block'" class="rounded-md bg-accent-light px-1.5 py-0.5 text-[10px] font-bold text-accent">
                Focus block
              </span>
            </div>
            <p class="mt-0.5 text-xs text-slate-400">{{ event.start_time || "Unscheduled" }}</p>
            <p v-if="linkedTask(event)" class="mt-1 text-xs text-slate-500">
              Task: {{ linkedTask(event)?.content }} · {{ linkedTask(event)?.completed_minutes }}/{{ linkedTask(event)?.scheduled_minutes }} min
            </p>
          </div>

          <!-- Right: actions -->
          <div class="flex shrink-0 flex-wrap gap-1.5">
            <template v-if="canResolveFocusBlock(event)">
              <button
                type="button"
                class="rounded-lg bg-positive px-2.5 py-1.5 text-[11px] font-semibold text-white transition hover:bg-emerald-600"
                @click="emit('update-status', event.id, 'completed')"
              >
                Done
              </button>
              <button
                type="button"
                class="rounded-lg border border-danger/20 bg-danger-light px-2.5 py-1.5 text-[11px] font-semibold text-danger transition hover:bg-red-100"
                @click="emit('update-status', event.id, 'canceled')"
              >
                Cancel
              </button>
              <button
                v-if="linkedTask(event)"
                type="button"
                class="rounded-lg border border-accent/20 bg-accent-light px-2.5 py-1.5 text-[11px] font-semibold text-accent transition hover:bg-indigo-100"
                @click="askAssistantAboutTask(event)"
              >
                Ask AI
              </button>
            </template>
            <button
              v-if="event.source !== 'google_imported'"
              type="button"
              class="rounded-lg border border-danger/20 bg-danger-light px-2.5 py-1.5 text-[11px] font-semibold text-danger transition hover:bg-red-100"
              @click="emit('delete-event', event.id)"
            >
              Delete
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Departure guides -->
    <div v-if="departureGuides.length" class="border-t border-slate-100 px-5 py-4">
      <p class="mb-3 text-xs font-semibold uppercase tracking-[0.22em] text-slate-400">Departure Guides</p>
      <div class="grid gap-2 md:grid-cols-2">
        <div
          v-for="event in departureGuides"
          :key="`dep-${event.id}`"
          class="rounded-xl border border-warn/20 bg-warn-light px-4 py-3"
        >
          <p class="text-sm font-semibold text-ink">{{ event.title }}</p>
          <p class="mt-0.5 text-xs text-slate-500">{{ event.location_name || "Unknown destination" }}</p>
          <p class="mt-2 text-xs font-semibold text-warn">
            Leave at {{ event.departure_time }} · {{ event.travel_duration_minutes }} min · {{ event.travel_mode || "route" }}
          </p>
        </div>
      </div>
    </div>
  </section>
</template>

<style>
.calendar-shell .fc-button {
  background: white !important;
  border: 1px solid #e2e8f0 !important;
  color: #1a1f2e !important;
  border-radius: 0.5rem !important;
  font-size: 0.75rem !important;
  font-weight: 600 !important;
  padding: 0.35rem 0.75rem !important;
  transition: all 0.15s !important;
}
.calendar-shell .fc-button:hover {
  background: #eef2ff !important;
  border-color: #4f46e5 !important;
  color: #4f46e5 !important;
}
.calendar-shell .fc-button-active,
.calendar-shell .fc-button:focus {
  background: #4f46e5 !important;
  border-color: #4f46e5 !important;
  color: white !important;
  box-shadow: none !important;
}
.calendar-shell .fc-toolbar-title {
  font-size: 1rem !important;
  font-weight: 700 !important;
  color: #1a1f2e !important;
}
.calendar-shell .event-local {
  background-color: #4f46e5 !important;
  border-color: #4338ca !important;
}
.calendar-shell .event-google {
  background-color: #0ea5e9 !important;
  border-color: #0284c7 !important;
}
.calendar-shell .event-focus-block {
  background-color: #7c3aed !important;
  border-color: #6d28d9 !important;
}
.calendar-shell .fc-timegrid-now-indicator-line {
  border-color: #dc2626 !important;
}
</style>
