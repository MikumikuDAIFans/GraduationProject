<script setup lang="ts">
import { computed, ref, watch } from "vue";
import type { Reminder, Suggestion, TaskItem } from "@/stores/workspace";

const props = defineProps<{
  reminders: Reminder[];
  todaySuggestions: Suggestion[];
  nextSuggestions: Suggestion[];
  tasks: TaskItem[];
  focusedTaskId?: number | null;
}>();
const emit = defineEmits<{ send: [message: string]; deleteTask: [taskId: number] }>();

type Tab = "tasks" | "reminders" | "suggestions";
const activeTab = ref<Tab>("tasks");
const focusedTaskRef = ref<HTMLElement | null>(null);

watch(() => props.focusedTaskId, (id) => {
  if (id != null) {
    activeTab.value = "tasks";
    requestAnimationFrame(() => focusedTaskRef.value?.scrollIntoView({ behavior: "smooth", block: "center" }));
  }
});

const taskMap = computed(() => new Map(props.tasks.map(t => [t.id, t])));
const allSuggestions = computed(() => [...props.todaySuggestions, ...props.nextSuggestions]);

const tabs = [
  { key: "tasks",       label: "Tasks",       count: () => props.tasks.length },
  { key: "reminders",   label: "Reminders",   count: () => props.reminders.length },
  { key: "suggestions", label: "Suggestions", count: () => allSuggestions.value.length },
] as const;

function isTaskFocused(t: TaskItem) { return props.focusedTaskId != null && t.id === props.focusedTaskId; }

function taskStatus(status?: string | null) {
  if (status === "done")        return { cls: "bg-positive-light text-positive", label: "Done" };
  if (status === "in_progress") return { cls: "bg-accent-light text-accent",    label: "In progress" };
  if (status === "scheduled")   return { cls: "bg-sky-50 text-sky-600",         label: "Scheduled" };
  return                               { cls: "bg-surface-3 text-ink-3",        label: status || "Pending" };
}

function suggestionStyle(type: string) {
  if (type === "departure_plan")  return { cls: "border-warn/20 bg-warn-light",      label: "Departure" };
  if (type === "weather_watch")   return { cls: "border-sky-200 bg-sky-50",          label: "Weather" };
  if (type === "task_split_slot") return { cls: "border-danger/20 bg-danger-light",  label: "Split slot" };
  if (type === "task_replan_slot")return { cls: "border-orange-200 bg-orange-50",    label: "Replan" };
  if (type === "task_resume_slot")return { cls: "border-accent/20 bg-accent-light",  label: "Resume" };
  return                                 { cls: "border-border bg-white",            label: "Slot" };
}

function reminderStyle(type: string) {
  if (type === "departure")     return { cls: "border-warn/20 bg-warn-light",     label: "Departure" };
  if (type === "event_start")   return { cls: "border-accent/20 bg-accent-light", label: "Event start" };
  if (type === "task_progress") return { cls: "border-positive/20 bg-positive-light", label: "Progress" };
  if (type === "task_replan")   return { cls: "border-danger/20 bg-danger-light", label: "Replan" };
  return                               { cls: "border-border bg-white",           label: type };
}

function slotMessage(s: Suggestion) {
  const task = s.related_task_id != null ? taskMap.value.get(s.related_task_id) : null;
  return task
    ? `帮我安排"${task.content}"，时间段 ${s.start_time} 到 ${s.end_time}`
    : `安排任务时间段 ${s.start_time} 到 ${s.end_time}`;
}
</script>

<template>
  <div class="rounded-xl border border-border bg-white shadow-card">
    <!-- Header + tabs -->
    <div class="border-b border-border px-4 pt-4 pb-0">
      <h2 class="mb-3 text-sm font-bold text-ink">Insights</h2>
      <div class="flex gap-0">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          type="button"
          class="flex items-center gap-1.5 border-b-2 px-3 pb-2.5 text-xs font-semibold transition-colors"
          :class="activeTab === tab.key
            ? 'border-accent text-accent'
            : 'border-transparent text-ink-3 hover:text-ink-2'"
          @click="activeTab = tab.key"
        >
          {{ tab.label }}
          <span
            class="rounded-full px-1.5 py-0.5 text-[10px] font-bold"
            :class="activeTab === tab.key ? 'bg-accent text-white' : 'bg-surface-3 text-ink-3'"
          >{{ tab.count() }}</span>
        </button>
      </div>
    </div>

    <div class="p-4">

      <!-- TASKS -->
      <div v-if="activeTab === 'tasks'">
        <div v-if="tasks.length" class="space-y-2">
          <div
            v-for="task in tasks"
            :key="task.id"
            :ref="(el) => { if (isTaskFocused(task)) focusedTaskRef = el as HTMLElement; }"
            class="rounded-lg border p-3 transition-all duration-200"
            :class="isTaskFocused(task)
              ? 'border-accent/30 bg-accent-light ring-2 ring-accent/15'
              : 'border-border bg-surface-2 hover:border-border-2'"
          >
            <div class="flex items-start justify-between gap-2">
              <div class="min-w-0 flex-1">
                <div class="flex flex-wrap items-center gap-2">
                  <p class="text-sm font-medium text-ink">{{ task.content }}</p>
                  <span class="rounded-md px-1.5 py-0.5 text-[10px] font-semibold" :class="taskStatus(task.status).cls">
                    {{ taskStatus(task.status).label }}
                  </span>
                </div>
                <div class="mt-1 flex flex-wrap gap-3 text-xs text-ink-3">
                  <span v-if="task.scheduled_minutes">{{ task.scheduled_minutes }} min scheduled</span>
                  <span v-if="task.completed_minutes">{{ task.completed_minutes }} min done</span>
                  <span v-if="task.remaining_minutes != null" class="font-medium text-ink-2">{{ task.remaining_minutes }} min left</span>
                </div>
                <!-- Progress bar -->
                <div v-if="task.scheduled_minutes && task.scheduled_minutes > 0" class="mt-2">
                  <div class="h-1 w-full overflow-hidden rounded-full bg-surface-3">
                    <div
                      class="h-full rounded-full bg-accent transition-all"
                      :style="{ width: `${Math.min(100, ((task.completed_minutes ?? 0) / task.scheduled_minutes) * 100)}%` }"
                    />
                  </div>
                </div>
              </div>
              <div class="flex shrink-0 gap-1.5">
                <button
                  type="button"
                  class="rounded-lg border border-border bg-white px-2.5 py-1.5 text-[11px] font-semibold text-ink-2 transition hover:bg-surface-3"
                  @click="emit('send', `继续安排任务 ${task.content}`)"
                >Plan</button>
                <button
                  type="button"
                  class="rounded-lg border border-danger/20 bg-danger-light px-2.5 py-1.5 text-[11px] font-semibold text-danger transition hover:bg-red-100"
                  @click="emit('deleteTask', task.id)"
                >Del</button>
              </div>
            </div>
          </div>
        </div>
        <div v-else class="rounded-lg border border-dashed border-border py-8 text-center">
          <p class="text-sm text-ink-3">No tracked tasks yet.</p>
          <p class="mt-1 text-xs text-ink-3">Ask the assistant to create a task.</p>
        </div>
      </div>

      <!-- REMINDERS -->
      <div v-else-if="activeTab === 'reminders'">
        <div v-if="reminders.length" class="space-y-2">
          <div
            v-for="reminder in reminders"
            :key="reminder.id"
            class="rounded-lg border p-3"
            :class="reminderStyle(reminder.remind_type).cls"
          >
            <p class="text-[10px] font-bold uppercase tracking-widest text-ink-3">
              {{ reminderStyle(reminder.remind_type).label }}
            </p>
            <p class="mt-1 text-sm font-medium text-ink">{{ reminder.message || reminder.remind_type }}</p>
            <p class="mt-0.5 text-xs text-ink-3">{{ reminder.remind_at }}</p>
          </div>
        </div>
        <div v-else class="rounded-lg border border-dashed border-border py-8 text-center">
          <p class="text-sm text-ink-3">No reminders scheduled.</p>
        </div>
      </div>

      <!-- SUGGESTIONS -->
      <div v-else-if="activeTab === 'suggestions'">
        <div v-if="allSuggestions.length" class="space-y-2">
          <div
            v-for="suggestion in allSuggestions"
            :key="`${suggestion.type}-${suggestion.start_time}`"
            class="rounded-lg border p-3"
            :class="suggestionStyle(suggestion.type).cls"
          >
            <div class="flex flex-wrap items-start justify-between gap-2">
              <div class="min-w-0 flex-1">
                <p class="text-[10px] font-bold uppercase tracking-widest text-ink-3">
                  {{ suggestionStyle(suggestion.type).label }}
                  <span v-if="suggestion.segment_index && suggestion.segment_total" class="text-danger">
                    · Seg {{ suggestion.segment_index }}/{{ suggestion.segment_total }}
                  </span>
                </p>
                <p class="mt-1 text-sm font-medium text-ink">{{ suggestion.title }}</p>
                <p class="mt-0.5 text-xs text-ink-3">{{ suggestion.start_time }} → {{ suggestion.end_time }}</p>
                <p v-if="suggestion.description" class="mt-1 text-xs text-ink-3">{{ suggestion.description }}</p>
              </div>
              <button
                v-if="suggestion.related_task_id != null"
                type="button"
                class="shrink-0 rounded-lg border border-positive/20 bg-positive-light px-2.5 py-1.5 text-[11px] font-semibold text-positive transition hover:bg-emerald-100"
                @click="emit('send', slotMessage(suggestion))"
              >Use slot →</button>
            </div>
          </div>
        </div>
        <div v-else class="rounded-lg border border-dashed border-border py-8 text-center">
          <p class="text-sm text-ink-3">No suggestions yet.</p>
        </div>
      </div>

    </div>
  </div>
</template>
