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

const emit = defineEmits<{
  send: [message: string];
  deleteTask: [taskId: number];
}>();

type Tab = "tasks" | "reminders" | "suggestions";
const activeTab = ref<Tab>("tasks");

// Auto-switch to tasks tab when a task is focused
watch(
  () => props.focusedTaskId,
  (id) => { if (id != null) activeTab.value = "tasks"; },
);

const taskMap = computed(() => new Map(props.tasks.map((t) => [t.id, t])));
const allSuggestions = computed(() => [...props.todaySuggestions, ...props.nextSuggestions]);
const focusedTaskRef = ref<HTMLElement | null>(null);

watch(
  () => props.focusedTaskId,
  (id) => {
    if (id != null) {
      requestAnimationFrame(() => {
        focusedTaskRef.value?.scrollIntoView({ behavior: "smooth", block: "center" });
      });
    }
  },
);

function slotMessage(suggestion: Suggestion) {
  const task = suggestion.related_task_id != null ? taskMap.value.get(suggestion.related_task_id) : null;
  if (task) return `帮我安排"${task.content}"，时间段 ${suggestion.start_time} 到 ${suggestion.end_time}`;
  return `安排任务时间段 ${suggestion.start_time} 到 ${suggestion.end_time}`;
}

function isTaskFocused(task: TaskItem) {
  return props.focusedTaskId != null && task.id === props.focusedTaskId;
}

function taskStatusStyle(status?: string | null) {
  if (status === "done") return { cls: "bg-positive-light text-positive", label: "Done" };
  if (status === "in_progress") return { cls: "bg-accent-light text-accent", label: "In progress" };
  if (status === "scheduled") return { cls: "bg-sky-50 text-sky-600", label: "Scheduled" };
  return { cls: "bg-slate-100 text-slate-500", label: status || "Pending" };
}

function suggestionStyle(type: string) {
  if (type === "departure_plan") return { cls: "border-warn/20 bg-warn-light", label: "Departure" };
  if (type === "weather_watch") return { cls: "border-sky-200/60 bg-sky-50", label: "Weather" };
  if (type === "task_split_slot") return { cls: "border-danger/20 bg-danger-light", label: "Split slot" };
  if (type === "task_replan_slot") return { cls: "border-orange-200/60 bg-orange-50", label: "Replan" };
  if (type === "task_resume_slot") return { cls: "border-accent/20 bg-accent-light", label: "Resume" };
  return { cls: "border-slate-200 bg-white", label: "Slot" };
}

function reminderStyle(type: string) {
  if (type === "departure") return { cls: "border-warn/20 bg-warn-light", label: "Departure" };
  if (type === "event_start") return { cls: "border-accent/20 bg-accent-light", label: "Event start" };
  if (type === "task_progress") return { cls: "border-positive/20 bg-positive-light", label: "Task progress" };
  if (type === "task_replan") return { cls: "border-danger/20 bg-danger-light", label: "Replan" };
  return { cls: "border-slate-200 bg-white", label: type };
}

const tabs: { key: Tab; label: string; count: () => number }[] = [
  { key: "tasks", label: "Tasks", count: () => props.tasks.length },
  { key: "reminders", label: "Reminders", count: () => props.reminders.length },
  { key: "suggestions", label: "Suggestions", count: () => allSuggestions.value.length },
];
</script>

<template>
  <section class="rounded-2xl border border-white/70 bg-white/70 shadow-panel backdrop-blur-xl">
    <!-- Header + Tabs -->
    <div class="px-5 pt-4">
      <div class="mb-3 flex items-center justify-between gap-3">
        <h2 class="text-lg font-bold text-ink">Insights</h2>
      </div>
      <div class="flex gap-1 rounded-xl bg-slate-100 p-1">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          type="button"
          class="flex flex-1 items-center justify-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition-all"
          :class="activeTab === tab.key
            ? 'bg-white text-ink shadow-sm'
            : 'text-slate-500 hover:text-slate-700'"
          @click="activeTab = tab.key"
        >
          {{ tab.label }}
          <span
            class="rounded-full px-1.5 py-0.5 text-[10px] font-bold"
            :class="activeTab === tab.key ? 'bg-accent text-white' : 'bg-slate-200 text-slate-500'"
          >
            {{ tab.count() }}
          </span>
        </button>
      </div>
    </div>

    <div class="px-5 py-4">

      <!-- TASKS TAB -->
      <div v-if="activeTab === 'tasks'">
        <div v-if="tasks.length" class="space-y-2">
          <div
            v-for="task in tasks"
            :key="task.id"
            :ref="(el) => { if (isTaskFocused(task)) focusedTaskRef = el as HTMLElement; }"
            class="rounded-xl border px-4 py-3 transition-all duration-200"
            :class="isTaskFocused(task)
              ? 'border-accent/30 bg-accent-light ring-2 ring-accent/20 shadow-sm'
              : 'border-slate-100 bg-white/80 hover:border-slate-200'"
          >
            <div class="flex flex-wrap items-start justify-between gap-2">
              <div class="min-w-0 flex-1">
                <div class="flex flex-wrap items-center gap-2">
                  <p class="text-sm font-semibold text-ink">{{ task.content }}</p>
                  <span
                    class="rounded-md px-1.5 py-0.5 text-[10px] font-bold"
                    :class="taskStatusStyle(task.status).cls"
                  >
                    {{ taskStatusStyle(task.status).label }}
                  </span>
                </div>
                <div class="mt-1.5 flex flex-wrap gap-3 text-xs text-slate-400">
                  <span v-if="task.scheduled_minutes">Scheduled {{ task.scheduled_minutes }} min</span>
                  <span v-if="task.completed_minutes">Done {{ task.completed_minutes }} min</span>
                  <span v-if="task.remaining_minutes != null" class="font-semibold text-slate-500">{{ task.remaining_minutes }} min left</span>
                </div>
              </div>
              <button
                type="button"
                class="shrink-0 rounded-lg border border-accent/20 bg-accent-light px-2.5 py-1.5 text-[11px] font-semibold text-accent transition hover:bg-indigo-100"
                @click="emit('send', `继续安排任务 ${task.content}`)"
              >
                Plan →
              </button>
              <button
                type="button"
                class="shrink-0 rounded-lg border border-danger/20 bg-danger-light px-2.5 py-1.5 text-[11px] font-semibold text-danger transition hover:bg-red-100"
                @click="emit('deleteTask', task.id)"
              >
                Delete
              </button>
            </div>

            <!-- Progress bar -->
            <div v-if="task.scheduled_minutes && task.scheduled_minutes > 0" class="mt-2.5">
              <div class="h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
                <div
                  class="h-full rounded-full bg-accent transition-all"
                  :style="{ width: `${Math.min(100, ((task.completed_minutes ?? 0) / task.scheduled_minutes) * 100)}%` }"
                />
              </div>
            </div>
          </div>
        </div>
        <p v-else class="rounded-xl border border-dashed border-slate-200 py-8 text-center text-sm text-slate-400">
          No tracked tasks yet.<br />
          <span class="text-xs">Ask the assistant to create a task for you.</span>
        </p>
      </div>

      <!-- REMINDERS TAB -->
      <div v-if="activeTab === 'reminders'">
        <div v-if="reminders.length" class="space-y-2">
          <div
            v-for="reminder in reminders"
            :key="reminder.id"
            class="rounded-xl border px-4 py-3"
            :class="reminderStyle(reminder.remind_type).cls"
          >
            <div class="flex items-start gap-3">
              <div class="min-w-0 flex-1">
                <p class="text-[10px] font-bold uppercase tracking-[0.2em] text-slate-500">
                  {{ reminderStyle(reminder.remind_type).label }}
                </p>
                <p class="mt-1 text-sm font-semibold text-ink">{{ reminder.message || reminder.remind_type }}</p>
                <p class="mt-0.5 text-xs text-slate-400">{{ reminder.remind_at }}</p>
              </div>
            </div>
          </div>
        </div>
        <p v-else class="rounded-xl border border-dashed border-slate-200 py-8 text-center text-sm text-slate-400">
          No reminders scheduled.
        </p>
      </div>

      <!-- SUGGESTIONS TAB -->
      <div v-if="activeTab === 'suggestions'">
        <div v-if="allSuggestions.length" class="space-y-2">
          <div
            v-for="suggestion in allSuggestions"
            :key="`${suggestion.type}-${suggestion.start_time}`"
            class="rounded-xl border px-4 py-3"
            :class="suggestionStyle(suggestion.type).cls"
          >
            <div class="flex flex-wrap items-start justify-between gap-2">
              <div class="min-w-0 flex-1">
                <p class="text-[10px] font-bold uppercase tracking-[0.2em] text-slate-500">
                  {{ suggestionStyle(suggestion.type).label }}
                  <span
                    v-if="suggestion.segment_index && suggestion.segment_total"
                    class="ml-1 text-danger"
                  >
                    · Seg {{ suggestion.segment_index }}/{{ suggestion.segment_total }}
                  </span>
                </p>
                <p class="mt-1 text-sm font-semibold text-ink">{{ suggestion.title }}</p>
                <p class="mt-0.5 text-xs text-slate-400">{{ suggestion.start_time }} → {{ suggestion.end_time }}</p>
                <p v-if="suggestion.description" class="mt-1 text-xs text-slate-500">{{ suggestion.description }}</p>
              </div>
              <button
                v-if="suggestion.related_task_id != null"
                type="button"
                class="shrink-0 rounded-lg border border-positive/20 bg-positive-light px-2.5 py-1.5 text-[11px] font-semibold text-positive transition hover:bg-emerald-100"
                @click="emit('send', slotMessage(suggestion))"
              >
                Use slot →
              </button>
            </div>
          </div>
        </div>
        <p v-else class="rounded-xl border border-dashed border-slate-200 py-8 text-center text-sm text-slate-400">
          No suggestions yet.
        </p>
      </div>

    </div>
  </section>
</template>
