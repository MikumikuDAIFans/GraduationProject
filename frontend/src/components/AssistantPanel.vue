<script setup lang="ts">
import MarkdownIt from "markdown-it";
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import type { AssistantAction, AssistantMessage, AssistantSession } from "@/stores/workspace";
import { formatDateTime } from "@/utils/locale";

const props = defineProps<{
  messages: AssistantMessage[];
  sending: boolean;
  lastAssistantActions: AssistantAction[];
  assistantSessions: AssistantSession[];
  activeSessionId: number | null;
  creatingSession: boolean;
  archivingSession: boolean;
  clearingSession: boolean;
}>();

const emit = defineEmits<{
  send: [message: string];
  focusTask: [taskId: number];
  createSession: [];
  switchSession: [sessionId: number];
  archiveSession: [];
  clearSession: [];
}>();

const { t, locale } = useI18n();
const markdown = new MarkdownIt({
  breaks: true,
  linkify: true,
  html: false,
});

const draft = ref("");
const messageContainer = ref<HTMLElement | null>(null);
const canSend = computed(() => draft.value.trim().length > 0 && !props.sending);
const sessionBusy = computed(() => props.creatingSession || props.archivingSession || props.clearingSession);

function renderMarkdown(text: string): string {
  return markdown.render(text.replace(/<script.*?>.*?<\/script>/gis, "").trim());
}

function send() {
  const value = draft.value.trim();
  if (!value) return;
  emit("send", value);
  draft.value = "";
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
    send();
  }
}

function actionLabel(type: string) {
  const map: Record<string, string> = {
    create_event: t("assistantPanel.createdEvent"),
    create_task: t("assistantPanel.createdTask"),
    conflict_warning: t("assistantPanel.conflictWarning"),
    suggest_schedule: t("assistantPanel.scheduleProposal"),
    apply_schedule: t("assistantPanel.scheduleApplied"),
    propose_event: t("assistantPanel.eventProposal"),
    apply_event_proposal: t("assistantPanel.eventApplied"),
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

function formatSlot(start?: unknown, end?: unknown) {
  return `${formatDateTime(String(start ?? ""), locale.value)} → ${formatDateTime(String(end ?? ""), locale.value)}`;
}

function confirmCommand(type: string) {
  return locale.value === "zh-CN"
    ? type === "propose_event" ? "按这个建议创建" : "按这个安排执行"
    : "confirm";
}

function cancelCommand() {
  return locale.value === "zh-CN" ? "取消这个计划" : "cancel";
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
  <div class="flex h-full flex-col bg-white">
    <div class="border-b border-border px-4 py-3">
      <div class="flex items-center justify-between gap-3">
        <div class="flex items-center gap-2">
          <div class="flex h-7 w-7 items-center justify-center rounded-lg bg-accent-light">
            <svg class="h-4 w-4 text-accent" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" d="M7.5 8.25h9m-9 3H12m-9.75 1.51c0 1.6 1.123 2.994 2.707 3.227 1.129.166 2.27.293 3.423.379.35.026.67.21.865.501L12 21l2.755-4.133a1.14 1.14 0 0 1 .865-.501 48.172 48.172 0 0 0 3.423-.379c1.584-.233 2.707-1.626 2.707-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0 0 12 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018Z" />
            </svg>
          </div>
          <div>
            <p class="text-sm font-semibold text-ink">{{ t("app.dailyCopilot") }}</p>
            <p class="text-[10px] uppercase tracking-widest text-ink-3">{{ t("assistantPanel.activeSession") }}</p>
          </div>
          <span
            v-if="sending"
            class="rounded-full bg-accent-light px-2 py-0.5 text-[10px] font-semibold text-accent"
          >
            {{ t("common.thinking") }}
          </span>
        </div>
      </div>

      <div class="mt-3 grid grid-cols-[1fr_auto] gap-2">
        <select
          class="rounded-xl border border-border bg-surface-2 px-3 py-2 text-sm text-ink focus:border-accent/50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-accent/20"
          :value="activeSessionId ?? undefined"
          :disabled="sessionBusy"
          @change="emit('switchSession', Number(($event.target as HTMLSelectElement).value))"
        >
          <option v-if="!assistantSessions.length" value="">{{ t("assistantPanel.noSessions") }}</option>
          <option v-for="session in assistantSessions" :key="session.id" :value="session.id">
            {{ session.title }} · {{ formatDateTime(session.updated_at ?? session.created_at ?? "", locale) }}
          </option>
        </select>
        <button
          type="button"
          class="rounded-xl bg-accent px-3 py-2 text-sm font-semibold text-white transition hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-50"
          :disabled="creatingSession"
          @click="emit('createSession')"
        >
          {{ creatingSession ? t("common.loading") : t("assistantPanel.newChat") }}
        </button>
      </div>

      <div class="mt-2 flex flex-wrap gap-2">
        <button
          type="button"
          class="rounded-lg border border-border px-2.5 py-1 text-[11px] font-medium text-ink-3 transition hover:text-ink"
          :disabled="!activeSessionId || clearingSession"
          @click="emit('clearSession')"
        >
          {{ t("assistantPanel.clearChat") }}
        </button>
        <button
          type="button"
          class="rounded-lg border border-danger/20 bg-danger-light px-2.5 py-1 text-[11px] font-medium text-danger transition hover:bg-red-100"
          :disabled="!activeSessionId || archivingSession"
          @click="emit('archiveSession')"
        >
          {{ t("assistantPanel.archiveChat") }}
        </button>
      </div>
    </div>

    <div ref="messageContainer" class="flex-1 space-y-3 overflow-y-auto px-3 py-4">
      <div v-if="!messages.length && !sending" class="flex flex-col items-center justify-center py-16 text-center">
        <div class="mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-accent-light">
          <svg class="h-6 w-6 text-accent" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" d="M7.5 8.25h9m-9 3H12m-9.75 1.51c0 1.6 1.123 2.994 2.707 3.227 1.129.166 2.27.293 3.423.379.35.026.67.21.865.501L12 21l2.755-4.133a1.14 1.14 0 0 1 .865-.501 48.172 48.172 0 0 0 3.423-.379c1.584-.233 2.707-1.626 2.707-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0 0 12 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018Z" />
          </svg>
        </div>
        <p class="text-sm font-medium text-ink-2">{{ t("assistantPanel.emptyTitle") }}</p>
        <p class="mt-1 text-xs text-ink-3">{{ t("assistantPanel.emptyDesc") }}</p>
      </div>

      <div
        v-for="message in messages"
        :key="message.id"
        class="flex"
        :class="message.role === 'user' ? 'justify-end' : 'justify-start'"
      >
        <div v-if="message.role === 'assistant'" class="mr-2 mt-1 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-accent-light">
          <svg class="h-3.5 w-3.5 text-accent" fill="currentColor" viewBox="0 0 20 20">
            <path d="M10 2a8 8 0 1 0 0 16A8 8 0 0 0 10 2Zm0 14a6 6 0 1 1 0-12 6 6 0 0 1 0 12Z" opacity=".3" />
            <circle cx="10" cy="10" r="3" />
          </svg>
        </div>

        <div
          class="max-w-[80%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed"
          :class="message.role === 'user'
            ? 'rounded-br-sm bg-accent text-white'
            : 'rounded-bl-sm border border-border bg-surface-2 text-ink'"
        >
          <p v-if="message.role === 'user'" class="whitespace-pre-wrap">{{ message.content }}</p>
          <div v-else class="assistant-md-light" v-html="renderMarkdown(message.content)" />
        </div>
      </div>

      <template v-if="lastAssistantActions.length">
        <div
          v-for="(action, index) in lastAssistantActions"
          :key="`${action.type}-${index}`"
          class="ml-8 rounded-xl border border-border bg-white px-3 py-2.5 shadow-card"
        >
          <p class="text-[10px] font-bold uppercase tracking-widest text-accent">{{ actionLabel(action.type) }}</p>

          <div v-if="action.type === 'create_event' || action.type === 'conflict_warning'" class="mt-1.5">
            <p class="text-xs font-semibold text-ink">{{ action.payload.title }}</p>
            <p class="text-[11px] text-ink-3">{{ formatSlot(action.payload.start_time, action.payload.end_time) }}</p>
          </div>

          <div v-else-if="action.type === 'create_task'" class="mt-1.5">
            <p class="text-xs font-semibold text-ink">{{ action.payload.content }}</p>
            <p v-if="action.payload.deadline" class="text-[11px] text-ink-3">{{ formatDateTime(String(action.payload.deadline), locale) }}</p>
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
              <p class="text-ink-3">{{ formatSlot(item.start_time, item.end_time) }}</p>
            </div>
            <div class="flex gap-2 pt-1">
              <button
                type="button"
                class="rounded-lg bg-positive px-3 py-1.5 text-[11px] font-semibold text-white transition hover:bg-positive-hover"
                @click="emit('send', confirmCommand(action.type))"
              >
                {{ t("common.confirm") }}
              </button>
              <button
                type="button"
                class="rounded-lg border border-border px-3 py-1.5 text-[11px] font-semibold text-ink-3 transition hover:text-ink"
                @click="emit('send', cancelCommand())"
              >
                {{ t("common.cancel") }}
              </button>
            </div>
          </div>

          <div v-else-if="action.type === 'apply_schedule'" class="mt-1.5 space-y-1">
            <p class="text-[11px] text-ink-3">{{ action.payload.count || 0 }}</p>
            <div
              v-for="(item, i) in appliedItems(action)"
              :key="`${index}-ev-${i}`"
              class="rounded-lg border border-border bg-surface-2 px-2.5 py-1.5 text-xs"
            >
              <p class="font-semibold text-ink">{{ item.title }}</p>
              <p class="text-ink-3">{{ formatSlot(item.start_time, item.end_time) }}</p>
            </div>
            <div
              v-for="(task, i) in linkedTasks(action)"
              :key="`${index}-t-${i}`"
              class="rounded-lg border border-positive/30 bg-positive-light px-2.5 py-1.5 text-xs"
            >
              <p class="font-semibold text-positive">{{ task.content }}</p>
              <p class="text-positive/60">{{ task.scheduled_minutes }} min · {{ task.scheduled_blocks_count }} blocks</p>
            </div>
          </div>

          <div v-else-if="action.type === 'apply_event_proposal' && appliedEvent(action)" class="mt-1.5">
            <div class="rounded-lg border border-border bg-surface-2 px-2.5 py-1.5 text-xs">
              <p class="font-semibold text-ink">{{ appliedEvent(action)?.title }}</p>
              <p class="text-ink-3">{{ formatSlot(appliedEvent(action)?.start_time, appliedEvent(action)?.end_time) }}</p>
            </div>
          </div>
        </div>
      </template>

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

    <div class="shrink-0 border-t border-border bg-white px-3 py-3">
      <div class="flex gap-2">
        <textarea
          v-model="draft"
          rows="2"
          class="flex-1 resize-none rounded-xl border border-border bg-surface-2 px-3 py-2.5 text-sm text-ink placeholder:text-ink-3 focus:border-accent/50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-accent/20"
          :placeholder="t('assistantPanel.askPlaceholder')"
          @keydown="handleKeydown"
        />
        <button
          type="button"
          class="shrink-0 self-end rounded-xl bg-accent px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-40"
          :disabled="!canSend || sessionBusy"
          @click="send"
        >
          {{ t("common.send") }}
        </button>
      </div>
      <p class="mt-1.5 text-[10px] text-ink-3">{{ t("assistantPanel.sendHint") }}</p>
    </div>
  </div>
</template>
