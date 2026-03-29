<script setup lang="ts">
import type { AssistantSummary, AssistantSummaryCard } from "@/stores/workspace";

defineProps<{ summary: AssistantSummary | null }>();
const emit = defineEmits<{
  send: [message: string];
  focusTask: [taskId: number];
  focusEvent: [eventId: number];
  focusAssistant: [];
}>();

function toneCard(tone: string) {
  if (tone === "warning") return "border-warn/20 bg-warn-light";
  if (tone === "focus")   return "border-accent/20 bg-accent-light";
  if (tone === "action")  return "border-positive/20 bg-positive-light";
  return "border-border bg-white";
}
function toneText(tone: string) {
  if (tone === "warning") return "text-warn";
  if (tone === "focus")   return "text-accent";
  if (tone === "action")  return "text-positive";
  return "text-ink-3";
}
function toneBadge(tone: string) {
  if (tone === "warning") return "bg-warn text-white";
  if (tone === "focus")   return "bg-accent text-white";
  if (tone === "action")  return "bg-positive text-white";
  return "bg-surface-3 text-ink-3";
}

function handleCardClick(card: AssistantSummaryCard) {
  if (card.related_task_id != null)  emit("focusTask", card.related_task_id);
  else if (card.related_event_id != null) emit("focusEvent", card.related_event_id);
  else if (card.thread_id) emit("focusAssistant");
}
</script>

<template>
  <div class="rounded-xl border border-border bg-white p-4 shadow-card">
    <div class="mb-3 flex items-center justify-between">
      <div class="flex items-center gap-2">
        <p class="text-xs font-bold text-ink-2">Assistant Digest</p>
        <span v-if="(summary?.unread_followups ?? 0) > 0"
          class="rounded-full bg-warn px-1.5 py-0.5 text-[10px] font-bold text-white">
          {{ summary?.unread_followups }}
        </span>
      </div>
      <span class="text-xs text-ink-3">{{ summary?.cards?.length ?? 0 }} items</span>
    </div>

    <!-- Horizontal scrolling cards -->
    <div v-if="summary?.cards?.length" class="scrollbar-hide -mx-1 flex gap-3 overflow-x-auto px-1 pb-1">
      <div
        v-for="card in summary.cards"
        :key="card.id"
        class="w-56 shrink-0 rounded-xl border p-3 transition-all duration-150"
        :class="[
          toneCard(card.tone),
          (card.related_task_id != null || card.related_event_id != null || card.thread_id)
            ? 'cursor-pointer hover:-translate-y-0.5 hover:shadow-card-md'
            : '',
        ]"
        @click="handleCardClick(card)"
      >
        <div class="mb-1.5 flex items-start justify-between gap-2">
          <p class="text-[10px] font-bold uppercase tracking-widest" :class="toneText(card.tone)">{{ card.title }}</p>
          <span v-if="card.related_task_id != null || card.related_event_id != null || card.thread_id"
            class="shrink-0 rounded-md px-1.5 py-0.5 text-[10px] font-bold" :class="toneBadge(card.tone)">
            {{ card.related_task_id != null ? `T#${card.related_task_id}` : card.related_event_id != null ? `E#${card.related_event_id}` : '→' }}
          </span>
        </div>
        <p class="text-sm font-semibold leading-snug text-ink">{{ card.value }}</p>
        <p class="mt-1 text-xs leading-5 text-ink-3">{{ card.description }}</p>
        <button
          v-if="card.action_label && card.action_message"
          type="button"
          class="mt-2.5 rounded-lg bg-ink px-2.5 py-1.5 text-[11px] font-semibold text-white transition hover:bg-ink-2"
          @click.stop="emit('send', card.action_message!)"
        >{{ card.action_label }}</button>
      </div>
    </div>

    <p v-else class="text-sm text-ink-3">No digest yet — send the assistant a message to get started.</p>
  </div>
</template>
