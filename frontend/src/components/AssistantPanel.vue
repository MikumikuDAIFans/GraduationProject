<script setup lang="ts">
import MarkdownIt from "markdown-it";
import { computed, nextTick, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import type {
  AssistantAction,
  AssistantMemoryCandidate,
  AssistantMessage,
  AssistantProposal,
  AssistantProposalOption,
  AssistantRenderBlock,
  AssistantSignal,
  AssistantSession,
} from "@/stores/workspace";
import { formatDateTime } from "@/utils/locale";

const props = defineProps<{
  messages: AssistantMessage[];
  sending: boolean;
  lastAssistantActions: AssistantAction[];
  assistantProposals: AssistantProposal[];
  assistantSignals: AssistantSignal[];
  assistantMemoryCandidates: AssistantMemoryCandidate[];
  assistantSessions: AssistantSession[];
  activeSessionId: number | null;
  loadingProposals: boolean;
  loadingSignals: boolean;
  loadingMemoryCandidates: boolean;
  creatingSession: boolean;
  archivingSession: boolean;
  clearingSession: boolean;
  proposalBusyId: number | null;
  memoryCandidateBusyId: number | null;
}>();

const emit = defineEmits<{
  send: [message: string];
  focusTask: [taskId: number];
  fetchProposals: [];
  fetchSignals: [];
  fetchMemoryCandidates: [];
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
const locallySubmitting = ref(false);
const locallySubmittedProposalIds = ref<Set<number>>(new Set());
const locallySubmittedInlineProposalIds = ref<Set<number>>(new Set());
const locallySubmittedMemoryCandidateIds = ref<Set<number>>(new Set());
let sendUnlockTimer: number | null = null;
const messageContainer = ref<HTMLElement | null>(null);
const sessionBusy = computed(() => props.creatingSession || props.archivingSession || props.clearingSession);
const canSend = computed(() => draft.value.trim().length > 0 && !props.sending && !locallySubmitting.value && !sessionBusy.value);
const isSending = computed(() => props.sending || locallySubmitting.value);
const visibleProposals = computed(() =>
  props.assistantProposals
    .filter((proposal) => ["pending", "execution_failed"].includes(proposal.status))
    .filter((proposal) => !locallySubmittedProposalIds.value.has(proposal.id))
    .slice(0, 5),
);
const visibleSignals = computed(() =>
  props.assistantSignals
    .filter((signal) => ["new", "evaluated", "proposal_created"].includes(signal.status))
    .slice(0, 5),
);
const visibleMemoryCandidates = computed(() =>
  props.assistantMemoryCandidates
    .filter((candidate) => !locallySubmittedMemoryCandidateIds.value.has(candidate.id))
    .slice(0, 5),
);
const proposalProtocolLabels = computed(() => {
  const entries = props.assistantProposals
    .filter((proposal) => proposal.status === "pending")
    .slice()
    .sort((left, right) => left.id - right.id)
    .map((proposal, index) => [proposal.id, `P${index + 1}`] as const);
  return new Map(entries);
});

function renderMarkdown(text: string): string {
  return markdown.render(text.replace(/<script.*?>.*?<\/script>/gis, "").trim());
}

function send() {
  if (locallySubmitting.value || props.sending || sessionBusy.value) return;
  const value = draft.value.trim();
  if (!value) return;
  locallySubmitting.value = true;
  if (sendUnlockTimer !== null) window.clearTimeout(sendUnlockTimer);
  draft.value = "";
  emit("send", value);
  sendUnlockTimer = window.setTimeout(() => {
    if (!props.sending) {
      locallySubmitting.value = false;
    }
    sendUnlockTimer = null;
  }, 800);
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
    send();
  }
}

function scrollMessagesToBottom(behavior: ScrollBehavior = "smooth") {
  nextTick(() => requestAnimationFrame(() => requestAnimationFrame(() => {
    const container = messageContainer.value;
    if (!container) return;
    container.scrollTo({ top: container.scrollHeight, behavior });
  })));
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

function proposalOptions(proposal: AssistantProposal): AssistantProposalOption[] {
  const options = proposal.payload_json?.options;
  return Array.isArray(options) ? options : [];
}

function proposalById(proposalId?: number) {
  if (typeof proposalId !== "number") return null;
  return props.assistantProposals.find((proposal) => proposal.id === proposalId) ?? null;
}

type InlineProposalOption = {
  option_id?: string;
  title?: string;
  summary?: string | null;
  rationale?: string | null;
  recommended?: boolean;
  selected?: boolean;
  prompt_on_click?: string;
};

type InlineRejectOption = {
  title?: string;
  prompt_on_click?: string;
};

type InlineProposalPayload = {
  proposal_id?: number;
  protocol_label?: string;
  status?: string;
  summary?: string | null;
  selected_option_id?: string | null;
  locally_selected_option_id?: string | null;
  locally_rejected?: boolean;
  options?: InlineProposalOption[];
  reject_option?: InlineRejectOption;
};

function messageRenderBlocks(message: AssistantMessage): AssistantRenderBlock[] {
  const blocks = message.render_blocks ?? message.render_blocks_json ?? [];
  return Array.isArray(blocks) ? blocks : [];
}

function inlineProposalPayload(block: AssistantRenderBlock): InlineProposalPayload {
  return (block.payload ?? {}) as InlineProposalPayload;
}

function inlineProposalOptions(block: AssistantRenderBlock): InlineProposalOption[] {
  const options = inlineProposalPayload(block).options;
  return Array.isArray(options) ? options : [];
}

function shouldRenderInlineProposalBlock(block: AssistantRenderBlock) {
  return block.type === "proposal_options";
}

function inlineProposalStatus(block: AssistantRenderBlock) {
  const payload = inlineProposalPayload(block);
  const currentProposal = proposalById(payload.proposal_id);
  const proposalId = payload.proposal_id;
  if (typeof proposalId === "number" && locallySubmittedInlineProposalIds.value.has(proposalId)) {
    return payload.locally_rejected ? "rejected" : "execution_pending";
  }
  return currentProposal?.status ?? payload.status ?? "pending";
}

function isInlineProposalDisabled(block: AssistantRenderBlock) {
  return inlineProposalStatus(block) !== "pending";
}

function isInlineOptionSelected(block: AssistantRenderBlock, option: InlineProposalOption) {
  const payload = inlineProposalPayload(block);
  const currentProposal = proposalById(payload.proposal_id);
  const selectedOptionId = currentProposal?.selected_option_id ?? payload.locally_selected_option_id ?? payload.selected_option_id;
  return Boolean(option.selected || (selectedOptionId && option.option_id === selectedOptionId));
}

function inlineProposalStatusLabel(block: AssistantRenderBlock) {
  return proposalStatusLabel(inlineProposalStatus(block));
}

function inlineProposalCardClass(block: AssistantRenderBlock) {
  return isInlineProposalDisabled(block)
    ? "border-border bg-surface-2 shadow-none"
    : "border-border bg-white shadow-card";
}

function inlineOptionClass(block: AssistantRenderBlock, option: InlineProposalOption) {
  if (!isInlineProposalDisabled(block)) {
    return isInlineOptionSelected(block, option)
      ? "border-accent bg-accent-light text-accent cursor-pointer"
      : "border-border bg-surface-2 text-ink hover:border-accent/40 hover:bg-white cursor-pointer";
  }
  return isInlineOptionSelected(block, option)
    ? "border-border bg-surface-3 text-ink"
    : "border-border bg-surface-2 text-ink-3";
}

function submitInlineProposalPrompt(block: AssistantRenderBlock, prompt?: string, optionId?: string) {
  const payload = inlineProposalPayload(block);
  if (!prompt || isInlineProposalDisabled(block)) return;
  if (typeof payload.proposal_id === "number") {
    locallySubmittedInlineProposalIds.value = new Set([...locallySubmittedInlineProposalIds.value, payload.proposal_id]);
    payload.locally_selected_option_id = optionId ?? null;
    payload.locally_rejected = !optionId;
    markProposalSubmitted(payload.proposal_id);
  }
  draft.value = prompt;
  emit("send", prompt);
  draft.value = "";
}

function proposalStatusLabel(status: string) {
  const map: Record<string, string> = {
    pending: t("assistantPanel.proposalPending"),
    accepted: t("assistantPanel.proposalAccepted"),
    execution_pending: t("assistantPanel.proposalExecuting"),
    executed: t("assistantPanel.proposalExecuted"),
    execution_failed: t("assistantPanel.proposalFailed"),
    rejected: t("assistantPanel.proposalRejected"),
    expired: t("assistantPanel.proposalExpired"),
    superseded: t("assistantPanel.proposalSuperseded"),
  };
  return map[status] ?? status;
}

function proposalStatusClass(status: string) {
  if (status === "executed") return "border-positive/30 bg-positive-light text-positive";
  if (status === "execution_failed") return "border-danger/30 bg-danger-light text-danger";
  if (status === "execution_pending") return "border-accent/30 bg-accent-light text-accent";
  if (status === "rejected" || status === "expired" || status === "superseded") {
    return "border-border bg-surface-2 text-ink-3";
  }
  return "border-warn/30 bg-warn-light text-warn";
}

function proposalProtocolLabel(proposal: AssistantProposal) {
  const protocolLabel = proposal.payload_json?.protocol_label;
  if (typeof protocolLabel === "string" && protocolLabel.trim()) {
    return protocolLabel;
  }
  return proposalProtocolLabels.value.get(proposal.id) ?? `#${proposal.id}`;
}

function proposalExecutionSummary(proposal: AssistantProposal) {
  const execution = proposal.payload_json?.execution as { result?: { actions?: Array<Record<string, unknown>> } } | undefined;
  return execution?.result?.actions ?? [];
}

function signalTypeLabel(signal: AssistantSignal) {
  const map: Record<string, string> = {
    deadline_risk: t("assistantPanel.signalDeadlineRisk"),
    departure_readiness: t("assistantPanel.signalDeparture"),
    conflict_warning: t("assistantPanel.signalConflict"),
    daily_morning_review: t("assistantPanel.signalMorning"),
    daily_night_review: t("assistantPanel.signalNight"),
    proposal_followup: t("assistantPanel.signalProposalFollowup"),
  };
  return map[signal.signal_type] ?? signal.signal_type;
}

function signalToneClass(signal: AssistantSignal) {
  if (signal.signal_type === "departure_readiness" || signal.severity === "urgent") {
    return "border-danger/30 bg-danger-light text-danger";
  }
  if (signal.signal_type === "deadline_risk" || signal.severity === "negotiate") {
    return "border-warn/30 bg-warn-light text-warn";
  }
  return "border-accent/30 bg-accent-light text-accent";
}

function signalSource(signal: AssistantSignal) {
  return signal.source_job || signal.dedup_key || signal.signal_type;
}

function signalReason(signal: AssistantSignal) {
  const context = signal.context_json ?? {};
  if (signal.signal_type === "deadline_risk") {
    const content = typeof context["content"] === "string" ? context["content"] : signal.target_id;
    const deadline = typeof context["deadline"] === "string" ? formatDateTime(context["deadline"], locale.value) : null;
    return deadline
      ? `任务「${content}」截止时间接近：${deadline}。可回复“帮我安排补救方案”或“先忽略”。`
      : `任务「${content}」临近截止，需要跟进。可回复“帮我安排补救方案”或“先忽略”。`;
  }
  if (signal.signal_type === "departure_readiness") {
    const title = typeof context["title"] === "string" ? context["title"] : signal.target_id;
    const departure = typeof context["departure_time"] === "string" ? formatDateTime(context["departure_time"], locale.value) : null;
    const travel = typeof context["travel_duration_minutes"] === "number" ? context["travel_duration_minutes"] : null;
    const slack = typeof context["slack_minutes"] === "number" ? context["slack_minutes"] : null;
    const weather = context["weather_snapshot"] as { weather?: { text?: string } } | null;
    const parts = [`「${title}」即将到出发窗口`];
    if (departure) parts.push(`建议出发 ${departure}`);
    if (travel != null) parts.push(`预计通勤 ${travel} 分钟`);
    if (slack != null) parts.push(`冗余 ${slack} 分钟`);
    if (weather?.weather?.text) parts.push(`天气 ${weather.weather.text}`);
    return `${parts.join("，")}。可回复“我已经在了”或“今天不去了”。`;
  }
  if (signal.signal_type === "proposal_followup") {
    const summary = typeof context["proposal_summary"] === "string" ? context["proposal_summary"] : signal.target_id;
    const label = typeof context["protocol_label"] === "string" && context["protocol_label"].trim()
      ? context["protocol_label"].trim()
      : signal.target_id;
    return `待确认方案跟进：${label}「${summary}」已经等待超过 2 小时。可回复“按方案A安排”“修改方案”或“先不要安排”。`;
  }
  return typeof context["message"] === "string" ? context["message"] : t("assistantPanel.signalGenericReason");
}

function memoryTypeLabel(type: string) {
  const map: Record<string, string> = {
    preferences: t("assistantPanel.memoryPreferences"),
    places: t("assistantPanel.memoryPlaces"),
    habits: t("assistantPanel.memoryHabits"),
    glossary: t("assistantPanel.memoryGlossary"),
  };
  return map[type] ?? type;
}

function memoryCandidateTitle(candidate: AssistantMemoryCandidate) {
  const title = candidate.proposed_change_json?.title;
  if (typeof title === "string" && title.trim()) return title.trim();
  return memoryTypeLabel(candidate.memory_type);
}

function memoryCandidateContent(candidate: AssistantMemoryCandidate) {
  const content = candidate.proposed_change_json?.content;
  if (typeof content === "string" && content.trim()) return content.trim();
  return t("assistantPanel.memoryEmptyContent");
}

function canConfirmProposal(proposal: AssistantProposal) {
  return proposal.status === "pending";
}

function markProposalSubmitted(proposalId: number) {
  locallySubmittedProposalIds.value = new Set([...locallySubmittedProposalIds.value, proposalId]);
}

function sendProposalPrompt(proposal: AssistantProposal, message: string) {
  markProposalSubmitted(proposal.id);
  emit("send", message);
}

function sendMemoryPrompt(candidate: AssistantMemoryCandidate, message: string) {
  locallySubmittedMemoryCandidateIds.value = new Set([...locallySubmittedMemoryCandidateIds.value, candidate.id]);
  emit("send", message);
}

function buildProposalConfirmPrompt(proposal: AssistantProposal, optionId: string) {
  const label = proposalProtocolLabel(proposal);
  return locale.value === "zh-CN"
    ? `确认 ${label} 方案${optionId}`
    : `confirm ${label} option ${optionId}`;
}

function buildProposalRejectPrompt(proposal: AssistantProposal) {
  const label = proposalProtocolLabel(proposal);
  return locale.value === "zh-CN"
    ? `${label} 先不要安排`
    : `reject ${label}`;
}

function buildProposalRetryPrompt(proposal: AssistantProposal) {
  const label = proposalProtocolLabel(proposal);
  return locale.value === "zh-CN"
    ? `重试 ${label}`
    : `retry ${label}`;
}

function buildMemoryConfirmPrompt(candidate: AssistantMemoryCandidate) {
  return locale.value === "zh-CN"
    ? `记住 M${candidate.id}`
    : `save M${candidate.id}`;
}

function buildMemoryRejectPrompt(candidate: AssistantMemoryCandidate) {
  return locale.value === "zh-CN"
    ? `M${candidate.id} 不要记`
    : `reject M${candidate.id}`;
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
    scrollMessagesToBottom();
  },
  { flush: "post" },
);

watch(
  () => props.messages.map((message) => `${message.id}:${message.content.length}`).join("|"),
  () => {
    scrollMessagesToBottom();
  },
  { flush: "post" },
);

watch(
  () => props.sending,
  (sending) => {
    scrollMessagesToBottom(sending ? "smooth" : "auto");
  },
);

onMounted(() => {
  emit("fetchProposals");
  emit("fetchSignals");
  emit("fetchMemoryCandidates");
  scrollMessagesToBottom("auto");
});

watch(
  () => props.activeSessionId,
  () => {
    locallySubmittedProposalIds.value = new Set();
    locallySubmittedInlineProposalIds.value = new Set();
    locallySubmittedMemoryCandidateIds.value = new Set();
    emit("fetchProposals");
    emit("fetchSignals");
    emit("fetchMemoryCandidates");
    scrollMessagesToBottom("auto");
  },
  { flush: "post" },
);

watch(
  () => props.sending,
  (sending) => {
    if (!sending && !sendUnlockTimer) locallySubmitting.value = false;
  },
);
</script>

<template>
  <div class="flex h-full min-h-0 flex-col overflow-hidden bg-white">
    <div class="shrink-0 border-b border-border px-4 py-3">
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

      <div class="mt-3 grid grid-cols-[minmax(0,1fr)_auto] gap-2">
        <select
          class="min-w-0 w-full rounded-xl border border-border bg-surface-2 px-3 py-2 text-sm text-ink focus:border-accent/50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-accent/20"
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
          class="shrink-0 rounded-xl bg-accent px-3 py-2 text-sm font-semibold text-white transition hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-50"
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

    <div v-if="visibleSignals.length || loadingSignals" class="shrink-0 border-b border-border bg-surface-2 px-3 py-3">
      <div class="mb-2 flex items-center justify-between">
        <p class="text-xs font-semibold text-ink">{{ t("assistantPanel.activeFollowups") }}</p>
        <span v-if="loadingSignals" class="text-[10px] text-ink-3">{{ t("common.loading") }}</span>
      </div>

      <div class="max-h-32 space-y-2 overflow-y-auto sm:max-h-52">
        <div
          v-for="signal in visibleSignals"
          :key="signal.id"
          class="rounded-lg border border-border bg-white px-3 py-2.5 shadow-card"
        >
          <div class="flex flex-wrap items-center gap-1.5">
            <span
              class="rounded-full border px-2 py-0.5 text-[10px] font-semibold"
              :class="signalToneClass(signal)"
            >
              {{ signalTypeLabel(signal) }}
            </span>
            <span class="text-[10px] font-semibold uppercase tracking-widest text-ink-3">
              S{{ signal.id }}
            </span>
          </div>
          <p class="mt-1 text-xs font-semibold leading-snug text-ink">{{ signalReason(signal) }}</p>
          <p class="mt-0.5 text-[11px] leading-snug text-ink-3">
            {{ t("assistantPanel.signalSource") }}：{{ signalSource(signal) }}
          </p>
        </div>
      </div>
    </div>

    <div v-if="visibleMemoryCandidates.length || loadingMemoryCandidates" class="shrink-0 border-b border-border bg-surface-2 px-3 py-3">
      <div class="mb-2 flex items-center justify-between">
        <p class="text-xs font-semibold text-ink">{{ t("assistantPanel.memoryCandidates") }}</p>
        <span v-if="loadingMemoryCandidates" class="text-[10px] text-ink-3">{{ t("common.loading") }}</span>
      </div>

      <div class="max-h-36 space-y-2 overflow-y-auto sm:max-h-52">
        <div
          v-for="candidate in visibleMemoryCandidates"
          :key="candidate.id"
          class="rounded-lg border border-border bg-white px-3 py-2.5 shadow-card"
        >
          <div class="flex items-start justify-between gap-2">
            <div class="min-w-0">
              <div class="flex flex-wrap items-center gap-1.5">
                <span class="text-[10px] font-bold uppercase tracking-widest text-accent">M{{ candidate.id }}</span>
                <span class="rounded-full border border-accent/30 bg-accent-light px-2 py-0.5 text-[10px] font-semibold text-accent">
                  {{ memoryTypeLabel(candidate.memory_type) }}
                </span>
              </div>
              <p class="mt-1 text-xs font-semibold leading-snug text-ink">{{ memoryCandidateTitle(candidate) }}</p>
              <p class="mt-0.5 text-[11px] leading-snug text-ink-3">{{ memoryCandidateContent(candidate) }}</p>
              <p v-if="candidate.reason" class="mt-0.5 text-[11px] leading-snug text-ink-3">{{ candidate.reason }}</p>
            </div>
          </div>

          <div class="mt-2 flex gap-2 border-t border-border pt-2">
            <button
              type="button"
              class="rounded-lg bg-positive px-2.5 py-1 text-[11px] font-semibold text-white transition hover:bg-positive-hover disabled:cursor-not-allowed disabled:opacity-50"
              :disabled="sending || memoryCandidateBusyId === candidate.id"
              @click="sendMemoryPrompt(candidate, buildMemoryConfirmPrompt(candidate))"
            >
              {{ t("assistantPanel.confirmMemoryCandidate") }}
            </button>
            <button
              type="button"
              class="rounded-lg border border-danger/20 px-2.5 py-1 text-[11px] font-semibold text-danger transition hover:bg-danger-light disabled:cursor-not-allowed disabled:opacity-50"
              :disabled="sending || memoryCandidateBusyId === candidate.id"
              @click="sendMemoryPrompt(candidate, buildMemoryRejectPrompt(candidate))"
            >
              {{ t("assistantPanel.rejectMemoryCandidate") }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <div ref="messageContainer" class="min-h-0 flex-1 space-y-3 overflow-y-auto px-3 py-4">
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
          class="min-w-0 max-w-[88%] break-words rounded-2xl px-4 py-2.5 text-sm leading-relaxed sm:max-w-[80%]"
          :class="message.role === 'user'
            ? 'rounded-br-sm bg-accent text-white'
            : 'rounded-bl-sm border border-border bg-surface-2 text-ink'"
        >
          <p v-if="message.role === 'user'" class="whitespace-pre-wrap">{{ message.content }}</p>
          <template v-else>
            <div class="assistant-md-light" v-html="renderMarkdown(message.content)" />
            <div
              v-for="(block, blockIndex) in messageRenderBlocks(message)"
              :key="`${message.id}-block-${blockIndex}`"
              class="mt-3"
            >
              <div
                v-if="block.type === 'proposal_options' && shouldRenderInlineProposalBlock(block)"
                class="rounded-xl border p-3"
                :class="inlineProposalCardClass(block)"
              >
                <div class="flex items-start justify-between gap-3">
                  <div>
                    <p class="text-[10px] font-bold uppercase tracking-widest text-accent">AI 方案</p>
                    <p class="mt-1 text-xs font-semibold text-ink">{{ inlineProposalPayload(block).summary }}</p>
                  </div>
                  <span class="rounded-full border border-border px-2 py-0.5 text-[10px] font-semibold text-ink-3">
                    {{ inlineProposalStatusLabel(block) }}
                  </span>
                </div>
                <div class="mt-3 space-y-2">
                  <button
                    v-for="option in inlineProposalOptions(block)"
                    :key="option.option_id"
                    type="button"
                    class="w-full rounded-lg border px-3 py-2 text-left transition"
                    :class="[
                      inlineOptionClass(block, option),
                      isInlineProposalDisabled(block) ? 'cursor-not-allowed opacity-55' : 'cursor-pointer',
                    ]"
                    :disabled="isInlineProposalDisabled(block)"
                    @click="submitInlineProposalPrompt(block, option.prompt_on_click, option.option_id)"
                  >
                    <div class="flex items-center justify-between gap-3">
                      <div class="min-w-0">
                        <div class="flex flex-wrap items-center gap-2">
                          <span class="text-xs font-semibold">{{ option.option_id }}.</span>
                          <span class="text-xs font-semibold">{{ option.title }}</span>
                          <span
                            v-if="option.recommended"
                            class="rounded-full bg-positive-light px-2 py-0.5 text-[10px] font-semibold text-positive"
                          >
                            推荐
                          </span>
                        </div>
                        <p v-if="option.summary" class="mt-1 break-words text-[11px] leading-snug text-ink-3">{{ option.summary }}</p>
                        <p v-if="option.rationale" class="mt-0.5 break-words text-[11px] leading-snug text-ink-3">{{ option.rationale }}</p>
                      </div>
                      <span v-if="isInlineOptionSelected(block, option)" class="text-[10px] font-semibold text-ink-3">已选</span>
                    </div>
                  </button>
                  <button
                    v-if="inlineProposalPayload(block).reject_option?.prompt_on_click"
                    type="button"
                    class="w-full rounded-lg border border-dashed border-border px-3 py-2 text-left text-[11px] font-semibold text-ink-3 transition disabled:cursor-not-allowed disabled:opacity-55"
                    :class="isInlineProposalDisabled(block) ? 'bg-surface-2' : 'hover:border-danger/30 hover:bg-danger-light hover:text-danger'"
                    :disabled="isInlineProposalDisabled(block)"
                    @click="submitInlineProposalPrompt(block, inlineProposalPayload(block).reject_option?.prompt_on_click)"
                  >
                    {{ inlineProposalPayload(block).reject_option?.title || "拒绝全部方案" }}
                  </button>
                </div>
              </div>
            </div>
          </template>
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
          class="min-w-0 flex-1 resize-none rounded-xl border border-border bg-surface-2 px-3 py-2.5 text-sm text-ink placeholder:text-ink-3 focus:border-accent/50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-accent/20"
          :placeholder="t('assistantPanel.askPlaceholder')"
          :disabled="sessionBusy"
          @keydown="handleKeydown"
        />
        <button
          type="button"
          class="shrink-0 self-end rounded-xl bg-accent px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-40"
          :disabled="!canSend || sessionBusy"
          :aria-busy="isSending"
          @click="send"
        >
          {{ isSending ? t("common.loading") : t("common.send") }}
        </button>
      </div>
      <p class="mt-1.5 text-[10px] text-ink-3">{{ t("assistantPanel.sendHint") }}</p>
    </div>
  </div>
</template>

<style scoped>
.assistant-proposal-list {
  overscroll-behavior: contain;
}

.assistant-proposal-summary,
.assistant-proposal-option-title,
.assistant-proposal-detail,
.assistant-proposal-rationale {
  overflow-wrap: anywhere;
}

@media (max-width: 640px) {
  .assistant-proposal-summary,
  .assistant-proposal-detail {
    display: -webkit-box;
    overflow: hidden;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 2;
  }

  .assistant-proposal-rationale {
    display: none;
  }
}
</style>
