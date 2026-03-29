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

watch(() => [props.focusedEventId, props.focusedTaskId], () => {
  if (props.focusedEventId != null || props.focusedTaskId != null) {
    requestAnimationFrame(() => focusedCardRef.value?.scrollIntoView({ behavior: "smooth", block: "center" }));
  }
});

const calendarEvents = computed(() =>
  props.events.map(e => ({
    id: String(e.id),
    title: e.source === "google_imported" ? `☁ ${e.title}` : e.title,
    start: e.start_time ?? undefined,
    end: e.end_time ?? undefined,
    classNames: [
      e.source === "google_imported" ? "event-google" : "event-local",
      e.event_type === "focus_block" ? "event-focus-block" : "",
    ],
  }))
);

const departureGuides = computed(() => props.events.filter(e => e.departure_time && e.travel_duration_minutes));

const highlightedEvents = computed(() =>
  [...props.events]
    .filter(e => e.start_time || e.source === "google_imported")
    .sort((a, b) => (b.start_time ?? "").localeCompare(a.start_time ?? ""))
    .slice(0, 8)
);

const taskMap = computed(() => new Map(props.tasks.map(t => [t.id, t])));

function linkedTask(e: CalendarEvent) {
  return e.linked_task_id ? taskMap.value.get(e.linked_task_id) ?? null : null;
}
function canResolveFocusBlock(e: CalendarEvent) {
  return e.event_type === "focus_block" && e.status !== "completed" && e.status !== "canceled";
}
function isEventFocused(e: CalendarEvent) {
  if (props.focusedEventId != null && e.id === props.focusedEventId) return true;
  if (props.focusedTaskId != null && e.linked_task_id === props.focusedTaskId) return true;
  return false;
}
function askAssistantAboutTask(e: CalendarEvent) {
  const task = linkedTask(e);
  if (task) emit("send-assistant", `现在进展如何，接下来怎么安排任务"${task.content}"`);
}
function syncBadge(status?: string | null) {
  if (status === "synced")   return { label: "Synced",   cls: "bg-positive-light text-positive" };
  if (status === "sync_error") return { label: "Error",  cls: "bg-danger-light text-danger" };
  if (status === "imported") return { label: "Imported", cls: "bg-sky-50 text-sky-600" };
  return                            { label: "Local",    cls: "bg-surface-3 text-ink-3" };
}
</script>

<template>
  <div class="rounded-xl border border-border bg-white shadow-card">

    <!-- Header -->
    <div class="flex items-center justify-between border-b border-border px-4 py-3">
      <div>
        <p class="text-[10px] font-bold uppercase tracking-widest text-ink-3">Calendar</p>
        <h2 class="mt-0.5 text-sm font-bold text-ink">Workspace Timeline</h2>
      </div>
      <span
        class="rounded-md px-2 py-1 text-[11px] font-medium"
        :class="loading ? 'bg-warn-light text-warn' : 'bg-surface-3 text-ink-3'"
      >{{ loading ? "Syncing…" : `${events.length} events` }}</span>
    </div>

    <!-- FullCalendar -->
    <div class="border-b border-border px-4 py-3">
      <FullCalendar
        class="calendar-shell"
        :options="{
          plugins: [dayGridPlugin, timeGridPlugin, interactionPlugin],
          initialView: mobile ? 'timeGridDay' : 'timeGridWeek',
          headerToolbar: mobile
            ? { left: 'prev,next today', center: 'title', right: 'dayGridMonth,timeGridWeek,timeGridDay' }
            : { left: 'prev,next today', center: 'title', right: 'dayGridMonth,timeGridWeek,timeGridDay' },
          events: calendarEvents,
          height: 'auto',
          nowIndicator: true,
        }"
      />
    </div>

    <!-- Legend -->
    <div class="flex flex-wrap gap-2 border-b border-border px-4 py-2.5">
      <span class="rounded-md bg-accent-light px-2 py-0.5 text-[11px] font-medium text-accent">● Local</span>
      <span class="rounded-md bg-sky-50 px-2 py-0.5 text-[11px] font-medium text-sky-600">☁ Google</span>
      <span class="rounded-md bg-positive-light px-2 py-0.5 text-[11px] font-medium text-positive">✓ Synced</span>
      <span class="rounded-md bg-danger-light px-2 py-0.5 text-[11px] font-medium text-danger">⚠ Error</span>
    </div>

    <!-- Event list -->
    <div v-if="highlightedEvents.length" class="px-4 py-3">
      <p class="mb-2.5 text-[10px] font-bold uppercase tracking-widest text-ink-3">Recent Events</p>
      <div class="space-y-2">
        <div
          v-for="event in highlightedEvents"
          :key="`evt-${event.id}`"
          :ref="(el) => { if (isEventFocused(event)) focusedCardRef = el as HTMLElement; }"
          class="flex flex-wrap items-start gap-3 rounded-lg border p-3 transition-all duration-200"
          :class="isEventFocused(event)
            ? 'border-accent/30 bg-accent-light ring-2 ring-accent/15'
            : 'border-border bg-surface-2 hover:border-border-2'"
        >
          <!-- Info -->
          <div class="min-w-0 flex-1">
            <div class="flex flex-wrap items-center gap-1.5">
              <p class="text-sm font-medium text-ink">{{ event.title }}</p>
              <span class="rounded-md px-1.5 py-0.5 text-[10px] font-semibold" :class="syncBadge(event.sync_status).cls">
                {{ syncBadge(event.sync_status).label }}
              </span>
              <span v-if="event.event_type === 'focus_block'"
                class="rounded-md bg-purple-50 px-1.5 py-0.5 text-[10px] font-semibold text-purple-600">Focus</span>
            </div>
            <p class="mt-0.5 text-xs text-ink-3">{{ event.start_time || "Unscheduled" }}</p>
            <p v-if="linkedTask(event)" class="mt-0.5 text-xs text-ink-3">
              {{ linkedTask(event)?.content }} · {{ linkedTask(event)?.completed_minutes }}/{{ linkedTask(event)?.scheduled_minutes }} min
            </p>
          </div>

          <!-- Actions -->
          <div class="flex shrink-0 flex-wrap gap-1.5">
            <template v-if="canResolveFocusBlock(event)">
              <button type="button"
                class="rounded-lg bg-positive px-2.5 py-1.5 text-[11px] font-semibold text-white transition hover:bg-positive-hover"
                @click="emit('update-status', event.id, 'completed')">Done</button>
              <button type="button"
                class="rounded-lg border border-danger/20 bg-danger-light px-2.5 py-1.5 text-[11px] font-semibold text-danger transition hover:bg-red-100"
                @click="emit('update-status', event.id, 'canceled')">Cancel</button>
              <button v-if="linkedTask(event)" type="button"
                class="rounded-lg border border-border bg-white px-2.5 py-1.5 text-[11px] font-semibold text-ink-2 transition hover:bg-surface-3"
                @click="askAssistantAboutTask(event)">Ask AI</button>
            </template>
            <button v-if="event.source !== 'google_imported'" type="button"
              class="rounded-lg border border-danger/20 bg-danger-light px-2.5 py-1.5 text-[11px] font-semibold text-danger transition hover:bg-red-100"
              @click="emit('delete-event', event.id)">Del</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Departure guides -->
    <div v-if="departureGuides.length" class="border-t border-border px-4 py-3">
      <p class="mb-2.5 text-[10px] font-bold uppercase tracking-widest text-ink-3">Departure Guides</p>
      <div class="grid gap-2 sm:grid-cols-2">
        <div v-for="event in departureGuides" :key="`dep-${event.id}`"
          class="rounded-lg border border-warn/20 bg-warn-light p-3">
          <p class="text-sm font-medium text-ink">{{ event.title }}</p>
          <p class="mt-0.5 text-xs text-ink-3">{{ event.location_name || "Unknown" }}</p>
          <p class="mt-1.5 text-xs font-semibold text-warn">
            Leave {{ event.departure_time }} · {{ event.travel_duration_minutes }} min · {{ event.travel_mode || "route" }}
          </p>
        </div>
      </div>
    </div>

  </div>
</template>
