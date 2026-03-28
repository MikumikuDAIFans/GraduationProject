<script setup lang="ts">
import type { AssistantSummary, AssistantSummaryCard } from "@/stores/workspace";

defineProps<{
  summary: AssistantSummary | null;
}>();

const emit = defineEmits<{
  send: [message: string];
  focusTask: [taskId: number];
  focusEvent: [eventId: number];
  focusAssistant: [];
}>();

function toneClasses(tone: string) {
  if (tone === "warning") return "border-warn/20 bg-warn-light";
  if (tone === "focus") return "border-accent/20 bg-accent-light";
  if (tone === "action") return "border-positive/20 bg-positive-light";
  return "border-slate-200 bg-white";
}

function toneLabel(tone: string) {
  if (tone === "warning") return "text-warn";
  if (tone === "focus") return "text-accent";
  if (tone === "action") return "text-positive";
  return "text-slate-500";
}

function toneBadge(tone: string) {
  if (tone === "warning") return "bg-warn text-white";
  if (tone === "focus") return "bg-accent text-white";
  if (tone === "action") return "bg-positive text-white";
  return "bg-slate-200 text-slate-600";
}

function isNavigable(card: AssistantSummaryCard) {
  return card.related_task_id != null || card.related_event_id != null || card.thread_id;
}

function handleCardClick(card: AssistantSummaryCard) {
  if (card.related_task_id != null) {
    emit("focusTask", card.related_task_id);
  } else if (card.related_event_id != null) {
    emit("focusEvent", card.related_event_id);
  } else if (card.thread_id) {
    emit("focusAssistant");
  }
}
</script>

<template>
  <section class="rounded-2xl border border-white/70 bg-white/70 px-5 py-4 shadow-panel backdrop-blur-xl">
    <div class="mb-3 flex items-center justify-between gap-3">
      <div class="flex items-center gap-2.5">
        <h2 class="text-sm font-bold text-ink">Assistant Digest</h2>
        <span
          v-if="(summary?.unread_followups ?? 0) > 0"
          class="rounded-full bg-warn px-2 py-0.5 text-[11px] font-bold text-white"
        >
          {{ summary?.unread_followups }} unread
        </span>
      </div>
      <p class="text-xs text-slate-400">{{ summary?.cards?.length ?? 0 }} items</p>
    </div>

    <!-- Horizontal card strip -->
    <div
      v-if="summary?.cards?.length"
      class="flex gap-3 overflow-x-auto pb-1 scrollbar-hide"
    >
      <div
        v-for="card in summary.cards"
        :key="card.id"
        class="w-64 shrink-0 rounded-xl border px-4 py-3 transition-all duration-150"
        :class="[
          toneClasses(card.tone),
          isNavigable(card) ? 'cursor-pointer hover:shadow-md hover:-translate-y-0.5' : '',
        ]"
        @click="handleCardClick(card)"
      >
        <div class="mb-2 flex items-start justify-between gap-2">
          <p class="text-[10px] font-bold uppercase tracking-[0.22em]" :class="toneLabel(card.tone)">
            {{ card.title }}
          </p>
          <span
            v-if="card.related_task_id != null || card.related_event_id != null || card.thread_id"
            class="shrink-0 rounded-md px-1.5 py-0.5 text-[10px] font-bold"
            :class="toneBadge(card.tone)"
          >
            {{ card.related_task_id != null ? `T#${card.related_task_id}` : card.related_event_id != null ? `E#${card.related_event_id}` : '→' }}
          </span>
        </div>
        <p class="text-sm font-semibold leading-snug text-ink">{{ card.value }}</p>
        <p class="mt-1.5 text-xs leading-5 text-slate-500">{{ card.description }}</p>
        <button
          v-if="card.action_label && card.action_message"
          type="button"
          class="mt-3 rounded-lg bg-ink px-2.5 py-1.5 text-[11px] font-semibold text-white transition hover:bg-slate-700"
          @click.stop="emit('send', card.action_message!)"
        >
          {{ card.action_label }}
        </button>
      </div>
    </div>

    <p v-else class="text-sm text-slate-400">No digest yet — send the assistant a message to get started.</p>
  </section>
</template>

<style scoped>
.scrollbar-hide::-webkit-scrollbar {
  display: none;
}
.scrollbar-hide {
  -ms-overflow-style: none;
  scrollbar-width: none;
}
</style>
