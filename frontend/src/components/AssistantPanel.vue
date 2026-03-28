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

const canSend = computed(() => draft.value.trim().length > 0 && !props.sending);

function renderMarkdown(text: string): string {
  return marked.parse(text, { async: false }) as string;
}

function send() {
  const value = draft.value.trim();
  if (!value) return;
  emit("send", value);
  draft.value = "";
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
    send();
  }
}

function actionLabel(type: string) {
  if (type === "create_event") return "Created Event";
  if (type === "create_task") return "Created Task";
  if (type === "conflict_warning") return "Conflict Warning";
  if (type === "suggest_schedule") return "Schedule Proposal";
  if (type === "apply_schedule") return "Schedule Applied";
  if (type === "propose_event") return "Event Proposal";
  if (type === "apply_event_proposal") return "Event Applied";
  return type;
}

function scheduleItems(action: AssistantAction) {
  const payload = action.payload as { items?: Array<Record<string, unknown>> };
  return payload.items ?? [];
}

function appliedItems(action: AssistantAction) {
  const payload = action.payload as { created_events?: Array<Record<string, unknown>> };
  return payload.created_events ?? [];
}

function appliedEvent(action: AssistantAction) {
  const payload = action.payload as { created_event?: Record<string, unknown> };
  return payload.created_event ?? null;
}

function linkedTasks(action: AssistantAction) {
  const payload = action.payload as { linked_tasks?: Array<Record<string, unknown>> };
  return payload.linked_tasks ?? [];
}

function sendInboxAction(message: string | null | undefined) {
  if (!message) return;
  emit("send", message);
}

function markInbox(itemId: string, action: "read" | "archive") {
  emit("updateInbox", itemId, action);
}

function inboxEntries(item: AssistantInboxItem) {
  const meta = item.meta as { entries?: Array<Record<string, unknown>> } | undefined;
  return meta?.entries ?? [];
}

watch(
  () => props.messages.length,
  () => {
    requestAnimationFrame(() => {
      messageContainer.value?.scrollTo({
        top: messageContainer.value.scrollHeight,
        behavior: "smooth",
      });
    });
  },
);
</script>

<template>
  <section class="flex flex-col rounded-2xl border border-slate-700/60 bg-[#13181f] text-white shadow-panel" style="min-height: min(36rem, calc(100svh - 10rem)); max-height: calc(100svh - 8rem);">

    <!-- Panel header -->
    <div class="shrink-0 border-b border-white/8 px-5 py-4">
      <div class="flex items-center justify-between gap-3">
        <div>
          <p class="text-[10px] font-bold uppercase tracking-[0.28em] text-slate-500">Assistant</p>
          <h2 class="mt-0.5 text-base font-bold text-white">Daily Copilot</h2>
        </div>
        <div class="flex items-center gap-2">
          <span
            v-if="inboxUnreadTotal > 0"
            class="rounded-full bg-warn px-2.5 py-0.5 text-[11px] font-bold text-white"
          >
            {{ inboxUnreadTotal }} new
          </span>
          <span
            class="rounded-lg border px-2.5 py-1 text-[11px] font-semibold"
            :class="sending
              ? 'border-accent/30 bg-accent/10 text-accent-muted'
              : 'border-white/10 bg-white/5 text-slate-400'"
          >
            {{ sending ? "Thinking…" : "Gemini" }}
          </span>
        </div>
      </div>
    </div>

    <!-- Inbox items -->
    <div v-if="inboxItems.length" class="shrink-0 space-y-2 border-b border-white/8 px-4 py-3">
      <div
        v-for="item in inboxItems"
        :key="item.id"
        class="rounded-xl border px-3 py-2.5"
        :class="item.read ? 'border-white/8 bg-white/5' : 'border-warn/20 bg-warn/8'"
      >
        <p class="text-[10px] font-bold uppercase tracking-[0.2em]" :class="item.read ? 'text-slate-500' : 'text-warn'">
          {{ item.kind }}
        </p>
        <p class="mt-1 text-xs font-semibold text-white/90">{{ item.title }}</p>
        <p class="mt-0.5 text-xs leading-5 text-white/60">{{ item.description }}</p>
        <div v-if="item.kind === 'task_followup_group'" class="mt-2 space-y-1.5">
          <div
            v-for="(entry, i) in inboxEntries(item)"
            :key="`${item.id}-${i}`"
            class="rounded-lg border border-white/8 bg-white/5 px-2.5 py-1.5"
          >
            <p class="text-[10px] font-bold uppercase tracking-[0.15em] text-slate-400">{{ entry.kind || entry.title }}</p>
            <p class="mt-0.5 text-xs text-white/75">{{ entry.description }}</p>
          </div>
        </div>
        <div class="mt-2 flex flex-wrap gap-1.5">
          <button
            v-if="item.action_label && item.action_message"
            type="button"
            class="rounded-lg bg-white/10 px-2.5 py-1 text-[11px] font-semibold text-white transition hover:bg-white/20"
            @click="sendInboxAction(item.action_message)"
          >
            {{ item.action_label }}
          </button>
          <button
            type="button"
            class="rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-[10px] font-semibold text-slate-400 transition hover:bg-white/10"
            @click="markInbox(item.id, 'read')"
          >
            {{ item.read ? "Read" : "Mark read" }}
          </button>
          <button
            type="button"
            class="rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-[10px] font-semibold text-slate-400 transition hover:bg-white/10"
            @click="markInbox(item.id, 'archive')"
          >
            Archive
          </button>
          <button
            v-if="item.related_task_id != null"
            type="button"
            class="rounded-lg border border-accent/30 bg-accent/10 px-2 py-1 text-[10px] font-semibold text-accent-muted transition hover:bg-accent/20"
            @click="emit('focusTask', item.related_task_id!)"
          >
            View task →
          </button>
        </div>
      </div>
    </div>

    <!-- Messages -->
    <div ref="messageContainer" class="flex-1 space-y-3 overflow-y-auto px-4 py-3">
      <div
        v-for="message in messages"
        :key="message.id"
        class="flex"
        :class="message.role === 'user' ? 'justify-end' : 'justify-start'"
      >
        <div
          class="max-w-[85%] rounded-2xl px-3.5 py-2.5"
          :class="message.role === 'user'
            ? 'rounded-br-sm bg-accent/80 text-white'
            : 'rounded-bl-sm bg-white/10 text-white/90'"
        >
          <p v-if="message.role === 'user'" class="whitespace-pre-wrap text-sm leading-6">{{ message.content }}</p>
          <div v-else class="assistant-md text-sm leading-6" v-html="renderMarkdown(message.content)" />
        </div>
      </div>

      <!-- Thinking indicator -->
      <div v-if="sending" class="flex justify-start">
        <div class="rounded-2xl rounded-bl-sm bg-white/10 px-4 py-3">
          <div class="flex gap-1">
            <span class="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400 [animation-delay:-0.3s]" />
            <span class="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400 [animation-delay:-0.15s]" />
            <span class="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400" />
          </div>
        </div>
      </div>

      <div
        v-if="!messages.length && !inboxItems.length"
        class="rounded-xl border border-white/8 bg-white/5 px-4 py-5 text-center text-xs leading-6 text-slate-400"
      >
        Ask for scheduling, task planning,<br />commute timing, or weather-aware advice.
      </div>
    </div>

    <!-- Last actions -->
    <div v-if="lastAssistantActions.length" class="shrink-0 border-t border-white/8 px-4 py-3">
      <p class="mb-2 text-[10px] font-bold uppercase tracking-[0.22em] text-slate-500">Latest Actions</p>
      <div class="space-y-2">
        <div
          v-for="(action, index) in lastAssistantActions"
          :key="`${action.type}-${index}`"
          class="rounded-xl border border-white/8 bg-white/5 px-3 py-2.5"
        >
          <p class="text-[10px] font-bold uppercase tracking-[0.2em] text-accent-muted">{{ actionLabel(action.type) }}</p>

          <div v-if="action.type === 'create_event'" class="mt-1.5 text-xs text-white/80">
            <p class="font-semibold">{{ action.payload.title }}</p>
            <p class="text-white/50">{{ action.payload.start_time }} → {{ action.payload.end_time }}</p>
            <p v-if="action.payload.advice_summary" class="mt-1 text-warn/80">{{ action.payload.advice_summary }}</p>
          </div>

          <div v-else-if="action.type === 'create_task'" class="mt-1.5 text-xs text-white/80">
            <p class="font-semibold">{{ action.payload.content }}</p>
            <p v-if="action.payload.deadline" class="text-white/50">Deadline: {{ action.payload.deadline }}</p>
          </div>

          <div v-else-if="action.type === 'conflict_warning'" class="mt-1.5 text-xs text-warn/90">
            <p class="font-semibold">{{ action.payload.title }}</p>
            <p class="text-white/50">{{ action.payload.start_time }} → {{ action.payload.end_time }}</p>
          </div>

          <div v-else-if="action.type === 'suggest_schedule'" class="mt-1.5 space-y-1.5">
            <div
              v-for="(item, i) in scheduleItems(action)"
              :key="`${index}-${i}`"
              class="rounded-lg border border-white/8 bg-white/5 px-2.5 py-1.5 text-xs"
            >
              <p class="font-semibold text-white/90">{{ item.title || item.type }}</p>
              <p class="text-white/50">{{ item.start_time }} → {{ item.end_time }}</p>
            </div>
            <div class="flex gap-2 pt-1">
              <button
                type="button"
                class="rounded-lg bg-positive px-3 py-1.5 text-[11px] font-semibold text-white transition hover:bg-emerald-500"
                @click="emit('send', '按这个安排执行')"
              >
                Confirm
              </button>
              <button
                type="button"
                class="rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-[11px] font-semibold text-white/70 transition hover:bg-white/10"
                @click="emit('send', '取消这个计划')"
              >
                Cancel
              </button>
            </div>
          </div>

          <div v-else-if="action.type === 'propose_event'" class="mt-1.5 space-y-1.5">
            <div class="rounded-lg border border-white/8 bg-white/5 px-2.5 py-1.5 text-xs">
              <p class="font-semibold text-white/90">{{ action.payload.title }}</p>
              <p class="text-white/50">{{ action.payload.start_time }} → {{ action.payload.end_time }}</p>
              <p v-if="action.payload.advice_summary" class="mt-1 text-warn/80">{{ action.payload.advice_summary }}</p>
            </div>
            <div class="flex gap-2 pt-1">
              <button
                type="button"
                class="rounded-lg bg-positive px-3 py-1.5 text-[11px] font-semibold text-white transition hover:bg-emerald-500"
                @click="emit('send', '按这个建议创建')"
              >
                Create Event
              </button>
              <button
                type="button"
                class="rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-[11px] font-semibold text-white/70 transition hover:bg-white/10"
                @click="emit('send', '取消这个计划')"
              >
                Cancel
              </button>
            </div>
          </div>

          <div v-else-if="action.type === 'apply_schedule'" class="mt-1.5 space-y-1.5 text-xs">
            <p class="text-white/70">Created {{ action.payload.count || 0 }} block(s)</p>
            <div
              v-for="(item, i) in appliedItems(action)"
              :key="`${index}-ev-${i}`"
              class="rounded-lg border border-white/8 bg-white/5 px-2.5 py-1.5"
            >
              <p class="font-semibold text-white/90">{{ item.title }}</p>
              <p class="text-white/50">{{ item.start_time }} → {{ item.end_time }}</p>
            </div>
            <div
              v-for="(task, i) in linkedTasks(action)"
              :key="`${index}-t-${i}`"
              class="rounded-lg border border-positive/20 bg-positive/10 px-2.5 py-1.5"
            >
              <p class="font-semibold text-positive/90">{{ task.content }}</p>
              <p class="text-white/50">{{ task.scheduled_minutes }} min scheduled · {{ task.scheduled_blocks_count }} blocks</p>
            </div>
          </div>

          <div v-else-if="action.type === 'apply_event_proposal'" class="mt-1.5 text-xs">
            <div v-if="appliedEvent(action)" class="rounded-lg border border-white/8 bg-white/5 px-2.5 py-1.5">
              <p class="font-semibold text-white/90">{{ appliedEvent(action)?.title }}</p>
              <p class="text-white/50">{{ appliedEvent(action)?.start_time }} → {{ appliedEvent(action)?.end_time }}</p>
            </div>
          </div>

          <div v-else class="mt-1 text-[11px] text-white/40">{{ JSON.stringify(action.payload) }}</div>
        </div>
      </div>
    </div>

    <!-- Input area -->
    <div class="shrink-0 border-t border-white/8 px-4 py-3">
      <div class="flex gap-2">
        <textarea
          v-model="draft"
          rows="2"
          class="min-h-[4rem] flex-1 resize-none rounded-xl border border-white/10 bg-white/8 px-3.5 py-2.5 text-sm text-white placeholder:text-slate-500 focus:border-accent/50 focus:outline-none focus:ring-2 focus:ring-accent/10"
          placeholder="Ask about scheduling, tasks, or planning…"
          @keydown="handleKeydown"
        />
        <button
          type="button"
          class="shrink-0 self-end rounded-xl bg-accent px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-40"
          :disabled="!canSend"
          @click="send"
        >
          Send
        </button>
      </div>
      <p class="mt-1.5 text-[10px] text-slate-600">Ctrl+Enter to send</p>
    </div>
  </section>
</template>

<style scoped>
.assistant-md :deep(p) {
  margin-top: 0.4rem;
  margin-bottom: 0;
}
.assistant-md :deep(p:first-child) {
  margin-top: 0;
}
.assistant-md :deep(ul),
.assistant-md :deep(ol) {
  margin-top: 0.4rem;
  padding-left: 1.1rem;
}
.assistant-md :deep(li) {
  margin-top: 0.2rem;
}
.assistant-md :deep(strong) {
  color: rgba(255, 255, 255, 0.95);
  font-weight: 600;
}
.assistant-md :deep(h1),
.assistant-md :deep(h2),
.assistant-md :deep(h3) {
  font-size: 0.8rem;
  font-weight: 700;
  margin-top: 0.6rem;
  color: rgba(255, 255, 255, 0.95);
}
.assistant-md :deep(code) {
  background: rgba(255, 255, 255, 0.12);
  border-radius: 0.25rem;
  padding: 0.1em 0.35em;
  font-size: 0.78em;
}
</style>
