<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import LoadingSkeleton from "@/components/LoadingSkeleton.vue";
import type { TaskItem } from "@/stores/workspace";

const props = defineProps<{
  tasks: TaskItem[];
  focusedTaskId?: number | null;
  loading?: boolean;
}>();
const emit = defineEmits<{ send: [message: string]; deleteTask: [taskId: number] }>();
const { t } = useI18n();

const focusedTaskRef = ref<HTMLElement | null>(null);

watch(() => props.focusedTaskId, (id) => {
  if (id != null) {
    requestAnimationFrame(() => focusedTaskRef.value?.scrollIntoView({ behavior: "smooth", block: "center" }));
  }
});

function isTaskFocused(task: TaskItem) {
  return props.focusedTaskId != null && task.id === props.focusedTaskId;
}

function taskStatus(status?: string | null) {
  if (status === "done") return { cls: "bg-positive-light text-positive", label: t("common.done") };
  if (status === "in_progress") return { cls: "bg-accent-light text-accent", label: t("insights.inProgress") };
  if (status === "scheduled") return { cls: "bg-sky-50 text-sky-600", label: t("insights.scheduled") };
  return { cls: "bg-surface-3 text-ink-3", label: status || t("insights.pending") };
}

const activeTasks = computed(() => props.tasks.filter(t => t.status !== "done"));
const doneTasks = computed(() => props.tasks.filter(t => t.status === "done"));
</script>

<template>
  <div class="rounded-xl border border-border bg-white shadow-card">
    <div class="border-b border-border px-4 pt-4 pb-3">
      <div class="flex items-center justify-between">
        <h2 class="text-sm font-bold text-ink">{{ t("common.tasks") }}</h2>
        <span class="rounded-full bg-surface-3 px-2 py-0.5 text-xs font-semibold text-ink-3">
          {{ activeTasks.length }} {{ t("insights.pending") }}
        </span>
      </div>
    </div>

    <div class="p-4">
      <LoadingSkeleton v-if="loading" :lines="5" />

      <div v-else-if="tasks.length" class="space-y-2">
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
                <span v-if="task.completed_minutes">{{ t("calendarPanel.minutesDone", { count: task.completed_minutes }) }}</span>
                <span v-if="task.remaining_minutes != null" class="font-medium text-ink-2">
                  {{ t("calendarPanel.minutesLeft", { count: task.remaining_minutes }) }}
                </span>
              </div>
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
              >{{ t("insights.plan") }}</button>
              <button
                type="button"
                class="rounded-lg border border-danger/20 bg-danger-light px-2.5 py-1.5 text-[11px] font-semibold text-danger transition hover:bg-red-100"
                @click="emit('deleteTask', task.id)"
              >{{ t("common.delete") }}</button>
            </div>
          </div>
        </div>
      </div>

      <div v-else class="rounded-lg border border-dashed border-border py-8 text-center">
        <p class="text-sm text-ink-3">{{ t("insights.noTasks") }}</p>
        <p class="mt-1 text-xs text-ink-3">{{ t("insights.noTasksHint") }}</p>
      </div>
    </div>
  </div>
</template>
