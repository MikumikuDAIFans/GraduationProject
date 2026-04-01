<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { marked } from "marked";
import type { AssistantAction, AssistantInboxItem, AssistantMessage } from "@/stores/workspace";

const props = defineProps<{
  inboxItems: AssistantInboxItem[];
  inboxUnreadTotal: number;
  messages: AssistantMessage[];
  sending: boolean;
  lastAssistantActions: AssistantAction[];
}>();

const emit = defineEmits<{
  send: [message: string];
  updateInbox: [itemId: string, action: "read" | "archive"];
  focusTask: [taskId: number];
}>();

const draft = ref("");
const messageContainer = ref<HTMLElement | null>(null);
const inboxOpen = ref(false);
const archivedIds = ref<Set<string>>(new Set());
const canSend = computed(() => draft.value.trim().length > 0 && !props.sending);

// Inbox items filtered to hide locally-archived ones
const visibleInboxItems = computed(() =>
  props.inboxItems.filter((i) => !archivedIds.value.has(i.id) && !i.archived),
);

function renderMarkdown(text: string): string {
  // Strip raw markdown if it looks like unparsed output (safety net)
  return marked.parse(text, { async: false }) as string;
}

function send() {
  const value = draft.value.trim();
  if (!value) return;
  emit("send", value);
  draft.value = "";
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) send();
}

function archiveItem(id: string) {
  archivedIds.value.add(id);
  emit("updateInbox", id, "archive");
}

function markRead(id: string) {
  emit("updateInbox", id, "read");
}

function actionLabel(type: string) {
  const map: Record<string, string> = {
    create_event: "Created Event",
    create_task: "Created Task",
    conflict_warning: "Conflict Warning",
    suggest_schedule: "Schedule Proposal",
    apply_schedule: "Schedule Applied",
    propose_event: "Event Proposal",
    apply_event_proposal: "Event Applied",
  };
  return map[type] ?? type;
}

function scheduleItems(action: AssistantAction) {
  return (action.payload as { items?: Array<Record<string, unknown>> }).items ?? [];
}
function appliedItems(action: AssistantAction) {
  return (action.payload as { created_events?: Array<Record<string, unknown>> }).created_events ?? [];
}
function appliedEvent(action: AssistantAction) {
  return (action.payload as { created_event?: Record<string, unknown> }).created_event ?? null;
}
function linkedTasks(action: AssistantAction) {
  return (action.payload as { linked_tasks?: Array<Record<string, unknown>> }).linked_tasks ?? [];
}
function rescheduleAlternatives(action: AssistantAction) {
  return (action.payload as { alternatives?: Array<Record<string, unknown>> }).alternatives ?? [];
}

watch(
  () => props.messages.length,
  () => {
    requestAnimationFrame(() => {
      messageContainer.value?.scrollTo({ top: messageContainer.value.scrollHeight, behavior: "smooth" });
    });
  },
);
</script>

<template>
  <!-- Full-height flex column — parent must define height -->
  <div class="flex h-full flex-col bg-white">

    <!-- Header -->
    <div class="flex h-12 shrink-0 items-center justify-between border-b border-border px-4">
      <div class="flex items-center gap-2">
        <div class="flex h-7 w-7 items-center justify-center rounded-lg bg-accent-light">
          <svg class="h-4 w-4 text-accent" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" d="M7.5 8.25h9m-9 3H12m-9.75 1.51c0 1.6 1.123 2.994 2.707 3.227 1.129.166 2.27.293 3.423.379.35.026.67.21.865.501L12 21l2.755-4.133a1.14 1.14 0 0 1 .865-.501 48.172 48.172 0 0 0 3.423-.379c1.584-.233 2.707-1.626 2.707-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0 0 12 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018Z"/>
          </svg>
        </div>
        <span class="text-sm font-semibold text-ink">Daily Copilot</span>
        <span v-if="sending" class="rounded-full bg-accent-light px-2 py-0.5 text-[10px] font-semibold text-accent">Thinking…</span>
      </div>
      <!-- Inbox toggle -->
      <button
        v-if="visibleInboxItems.length"
        type="button"
        class="flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-1 text-xs font-medium text-ink-3 transition hover:border-border-2 hover:text-ink-2"
        @click="inboxOpen = !inboxOpen"
      >
        <span>Inbox</span>
        <span class="rounded-full bg-warn px-1.5 py-0.5 text-[10px] font-bold text-white leading-none">{{ visibleInboxItems.length }}</span>
        <svg class="h-3 w-3 transition-transform" :class="inboxOpen ? 'rotate-180' : ''" fill="none" viewBox="0 0 24 24" stroke-width="2.5" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" d="m19.5 8.25-7.5 7.5-7.5-7.5"/>
        </svg>
      </button>
    </div>

    <!-- Inbox drawer (collapsible) -->
    <div v-if="inboxOpen && visibleInboxItems.length" class="shrink-0 space-y-2 border-b border-border bg-surface-2 px-3 py-3">
      <div
        v-for="item in visibleInboxItems"
        :key="item.id"
        class="rounded-xl border bg-white px-3 py-2.5 shadow-card"
        :class="item.read ? 'border-border' : 'border-warn/40'"
      >
        <div class="flex items-start justify-between gap-2">
          <div class="min-w-0 flex-1">
            <p class="text-[10px] font-bold uppercase tracking-widest" :class="item.read ? 'text-ink-3' : 'text-warn'">
              {{ item.kind.replace(/_/g, ' ') }}
            </p>
            <p class="mt-0.5 text-xs font-semibold text-ink">{{ item.title }}</p>
            <p v-if="item.description" class="mt-0.5 text-[11px] leading-5 text-ink-3">{{ item.description }}</p>
          </div>
          <!-- Archive X button -->
          <button
            type="button"
            class="shrink-0 rounded-md p-1 text-ink-3 transition hover:bg-surface-3 hover:text-danger"
            title="Archive"
            @click="archiveItem(item.id)"
          >
            <svg class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" d="M6 18 18 6M6 6l12 12"/>
            </svg>
          </button>
        </div>

        <div class="mt-2 flex flex-wrap gap-1.5">
          <button
            v-if="item.action_label && item.action_message"
            type="button"
            class="rounded-md bg-accent px-2.5 py-1 text-[11px] font-semibold text-white transition hover:bg-accent-hover"
            @click="emit('send', item.action_message!)"
          >{{ item.action_label }}</button>
          <button
            v-if="!item.read"
            type="button"
            class="rounded-md border border-border px-2.5 py-1 text-[11px] text-ink-3 transition hover:text-ink"
            @click="markRead(item.id)"
          >Mark read</button>
          <button
            v-if="item.related_task_id != null"
            type="button"
            class="rounded-md border border-accent/30 bg-accent-light px-2.5 py-1 text-[11px] font-semibold text-accent transition hover:bg-accent/20"
            @click="emit('focusTask', item.related_task_id!)"
          >View task →</button>
        </div>
      </div>
    </div>

    <!-- Messages — fills remaining height and scrolls -->
    <div ref="messageContainer" class="flex-1 space-y-3 overflow-y-auto px-3 py-4">

      <!-- Empty state -->
      <div
        v-if="!messages.length && !sending"
        class="flex flex-col items-center justify-center py-16 text-center"
      >
        <div class="mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-accent-light">
          <svg class="h-6 w-6 text-accent" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" d="M7.5 8.25h9m-9 3H12m-9.75 1.51c0 1.6 1.123 2.994 2.707 3.227 1.129.166 2.27.293 3.423.379.35.026.67.21.865.501L12 21l2.755-4.133a1.14 1.14 0 0 1 .865-.501 48.172 48.172 0 0 0 3.423-.379c1.584-.233 2.707-1.626 2.707-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0 0 12 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018Z"/>
          </svg>
        </div>
        <p class="text-sm font-medium text-ink-2">Ask Daily Copilot</p>
        <p class="mt-1 text-xs text-ink-3">Scheduling, tasks, and weather-aware planning.</p>
      </div>

      <!-- Message bubbles -->
      <div
        v-for="message in messages"
        :key="message.id"
        class="flex"
        :class="message.role === 'user' ? 'justify-end' : 'justify-start'"
      >
        <!-- AI avatar dot -->
        <div v-if="message.role === 'assistant'" class="mr-2 mt-1 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-accent-light">
          <svg class="h-3.5 w-3.5 text-accent" fill="currentColor" viewBox="0 0 20 20">
            <path d="M10 2a8 8 0 1 0 0 16A8 8 0 0 0 10 2Zm0 14a6 6 0 1 1 0-12 6 6 0 0 1 0 12Z" opacity=".3"/>
            <circle cx="10" cy="10" r="3"/>
          </svg>
        </div>

        <div
          class="max-w-[80%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed"
          :class="message.role === 'user'
            ? 'rounded-br-sm bg-accent text-white'
            : 'rounded-bl-sm border border-border bg-surface-2 text-ink'"
        >
          <p v-if="message.role === 'user'" class="whitespace-pre-wrap">{{ message.content }}</p>
          <!-- AI: render markdown with light-mode prose styles -->
          <div v-else class="assistant-md-light" v-html="renderMarkdown(message.content)" />
        </div>
      </div>

      <!-- Inline action cards (after last AI message) -->
      <template v-if="lastAssistantActions.length">
        <div
          v-for="(action, index) in lastAssistantActions"
          :key="`${action.type}-${index}`"
          class="ml-8 rounded-xl border border-border bg-white px-3 py-2.5 shadow-card"
        >
          <p class="text-[10px] font-bold uppercase tracking-widest text-accent">{{ actionLabel(action.type) }}</p>

          <div v-if="action.type === 'create_event' || action.type === 'conflict_warning'" class="mt-1.5">
            <p class="text-xs font-semibold text-ink">{{ action.payload.title }}</p>
            <p class="text-[11px] text-ink-3">{{ action.payload.start_time }} → {{ action.payload.end_time }}</p>
          </div>

          <div v-else-if="action.type === 'create_task'" class="mt-1.5">
            <p class="text-xs font-semibold text-ink">{{ action.payload.content }}</p>
            <p v-if="action.payload.deadline" class="text-[11px] text-ink-3">Deadline: {{ action.payload.deadline }}</p>
          </div>

          <div v-else-if="action.type === 'suggest_schedule' || action.type === 'propose_event'" class="mt-2 space-y-1.5">
            <div
              v-for="(item, i) in action.type === 'suggest_schedule'
                ? scheduleItems(action)
                : [{ title: action.payload.title, start_time: action.payload.start_time, end_time: action.payload.end_time }]"
              :key="`${index}-${i}`"
              class="rounded-lg border border-border bg-surface-2 px-2.5 py-1.5 text-xs"
            >
              <p class="font-semibold text-ink">{{ item.title }}</p>
              <p class="text-ink-3">{{ item.start_time }} → {{ item.end_time }}</p>
            </div>
            <div class="flex gap-2 pt-1">
              <button
                type="button"
                class="rounded-lg bg-positive px-3 py-1.5 text-[11px] font-semibold text-white transition hover:bg-positive-hover"
                @click="emit('send', action.type === 'propose_event' ? '按这个建议创建' : '按这个安排执行')"
              >Confirm</button>
              <button
                type="button"
                class="rounded-lg border border-border px-3 py-1.5 text-[11px] font-semibold text-ink-3 transition hover:text-ink"
                @click="emit('send', '取消这个计划')"
              >Cancel</button>
            </div>
          </div>

          <div v-else-if="action.type === 'apply_schedule'" class="mt-1.5 space-y-1">
            <p class="text-[11px] text-ink-3">Created {{ action.payload.count || 0 }} block(s)</p>
            <div v-for="(item, i) in appliedItems(action)" :key="`${index}-ev-${i}`"
              class="rounded-lg border border-border bg-surface-2 px-2.5 py-1.5 text-xs">
              <p class="font-semibold text-ink">{{ item.title }}</p>
              <p class="text-ink-3">{{ item.start_time }} → {{ item.end_time }}</p>
            </div>
            <div v-for="(task, i) in linkedTasks(action)" :key="`${index}-t-${i}`"
              class="rounded-lg border border-positive/30 bg-positive-light px-2.5 py-1.5 text-xs">
              <p class="font-semibold text-positive">{{ task.content }}</p>
              <p class="text-positive/60">{{ task.scheduled_minutes }} min · {{ task.scheduled_blocks_count }} blocks</p>
            </div>
          </div>

          <div v-else-if="action.type === 'apply_event_proposal' && appliedEvent(action)" class="mt-1.5">
            <div class="rounded-lg border border-border bg-surface-2 px-2.5 py-1.5 text-xs">
              <p class="font-semibold text-ink">{{ appliedEvent(action)?.title }}</p>
              <p class="text-ink-3">{{ appliedEvent(action)?.start_time }} → {{ appliedEvent(action)?.end_time }}</p>
            </div>
          </div>

          <div v-else-if="action.type === 'suggest_reschedule'" class="mt-2 space-y-1.5">
            <p class="text-xs font-semibold text-accent">Alternative times for {{ action.payload.event_title }}</p>
            <div
              v-for="(alt, i) in rescheduleAlternatives(action)"
              :key="`${index}-alt-${i}`"
              class="flex items-center justify-between rounded-lg border border-border bg-surface-2 px-2.5 py-2 text-xs"
            >
              <span class="text-ink-3">{{ alt.start_time }} -> {{ alt.end_time }}</span>
              <button
                type="button"
                class="rounded-md bg-accent px-2.5 py-1 text-[11px] font-semibold text-white transition hover:bg-accent-hover"
                @click="emit('send', `Move ${action.payload.event_title} to ${alt.start_time} -> ${alt.end_time}`)"
              >Use</button>
            </div>
          </div>
        </div>
      </template>

      <!-- Thinking dots -->
      <div v-if="sending" class="flex justify-start">
        <div class="ml-8 rounded-2xl rounded-bl-sm border border-border bg-surface-2 px-4 py-3">
          <div class="flex gap-1">
            <span class="h-1.5 w-1.5 animate-bounce rounded-full bg-ink-3 [animation-delay:-0.3s]" />
            <span class="h-1.5 w-1.5 animate-bounce rounded-full bg-ink-3 [animation-delay:-0.15s]" />
            <span class="h-1.5 w-1.5 animate-bounce rounded-full bg-ink-3" />
          </div>
        </div>
      </div>

    </div>

    <!-- Input area -->
    <div class="shrink-0 border-t border-border bg-white px-3 py-3">
      <div class="flex gap-2">
        <textarea
          v-model="draft"
          rows="2"
          class="flex-1 resize-none rounded-xl border border-border bg-surface-2 px-3 py-2.5 text-sm text-ink placeholder:text-ink-3 focus:border-accent/50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-accent/20"
          placeholder="Ask about scheduling, tasks, or planning…"
          @keydown="handleKeydown"
        />
        <button
          type="button"
          class="shrink-0 self-end rounded-xl bg-accent px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-40"
          :disabled="!canSend"
          @click="send"
        >Send</button>
      </div>
      <p class="mt-1.5 text-[10px] text-ink-3">Ctrl+Enter to send</p>
    </div>

  </div>
</template>
