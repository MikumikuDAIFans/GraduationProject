import { defineStore } from "pinia";
import { api } from "@/api/client";
import { defaultInputAdapter } from "@/inputAdapters/textInput";
import { defaultOutputAdapter } from "@/outputAdapters/textOutput";

export interface AssistantAction {
  type: string;
  payload: Record<string, unknown>;
}

export interface AssistantInboxItem {
  id: string;
  kind: string;
  title: string;
  description: string;
  priority: number;
  thread_id?: string | null;
  read?: boolean;
  archived?: boolean;
  entry_count?: number | null;
  updated_at?: string | null;
  action_label?: string | null;
  action_message?: string | null;
  related_task_id?: number | null;
  related_event_id?: number | null;
  meta?: Record<string, unknown>;
}

export interface AssistantInbox {
  items: AssistantInboxItem[];
  total: number;
  unread_total: number;
}

export interface AssistantSummaryCard {
  id: string;
  title: string;
  value: string;
  description: string;
  tone: string;
  action_label?: string | null;
  action_message?: string | null;
  thread_id?: string | null;
  related_task_id?: number | null;
  related_event_id?: number | null;
  meta?: Record<string, unknown>;
}

export interface AssistantSummary {
  generated_at: string;
  unread_followups: number;
  cards: AssistantSummaryCard[];
}

export interface AssistantMessage {
  id: number | string;
  role: "user" | "assistant";
  content: string;
  tool_calls_json?: AssistantAction[] | null;
  created_at?: string;
}

export interface AssistantSession {
  id: number;
  user_id: string;
  session_type?: string | null;
  title: string;
  is_archived?: boolean;
  context_json?: Record<string, unknown> | null;
  created_at?: string | null;
  updated_at?: string | null;
  messages?: AssistantMessage[];
}

export interface AssistantProposalOption {
  option_id: string;
  title: string;
  summary?: string | null;
  actions?: Array<Record<string, unknown>>;
  rationale?: string | null;
}

export interface AssistantProposal {
  id: number;
  user_id: string;
  session_id?: number | null;
  thread_state_id?: number | null;
  proposal_type: string;
  trigger_type: string;
  status: string;
  dedup_key?: string | null;
  priority: number;
  summary: string;
  payload_json: {
    options?: AssistantProposalOption[];
    execution?: Record<string, unknown>;
    [key: string]: unknown;
  };
  recommended_option_id?: string | null;
  selected_option_id?: string | null;
  is_time_sensitive: boolean;
  related_task_id?: number | null;
  related_event_id?: number | null;
  source_signal_id?: number | null;
  supersedes_proposal_id?: number | null;
  expires_at?: string | null;
  followup_after?: string | null;
  confirmed_at?: string | null;
  execution_started_at?: string | null;
  execution_error?: string | null;
  executed_at?: string | null;
  archived_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface AssistantSignal {
  id: number;
  user_id: string;
  signal_type: string;
  severity: string;
  status: string;
  dedup_key?: string | null;
  target_type?: string | null;
  target_id?: number | null;
  context_json?: Record<string, unknown> | null;
  source_job?: string | null;
  cooldown_until?: string | null;
  evaluated_at?: string | null;
  proposal_created_at?: string | null;
  dismissed_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface AssistantMemoryCandidate {
  id: number;
  user_id: string;
  memory_type: "preferences" | "places" | "habits" | "glossary" | string;
  source_specialist: string;
  status: "proposed" | "confirmed" | "rejected" | "written" | string;
  confidence: number;
  proposed_change_json: {
    operation?: string;
    title?: string;
    content?: string;
    [key: string]: unknown;
  };
  reason?: string | null;
  dedup_key?: string | null;
  confirmed_at?: string | null;
  rejected_at?: string | null;
  written_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface AssistantMemoryFileSummary {
  memory_type: string;
  path: string;
  exists: boolean;
  line_count: number;
  updated_at?: string | null;
  preview: string[];
}

export interface AssistantMemoryRead {
  user_id: string;
  root: string;
  files: AssistantMemoryFileSummary[];
}

const ACTIVE_PROPOSAL_STATUSES = [
  "pending",
  "accepted",
  "execution_pending",
  "execution_failed",
];

const ACTIVE_MEMORY_CANDIDATE_STATUSES = ["proposed"];
const ACTIVE_SIGNAL_STATUSES = ["new", "evaluated", "proposal_created"];
const SEND_QUEUE_DELAY_MS = 120;

type AssistantTransportError = Error & {
  assistantRequestSent?: boolean;
};

function markAssistantRequestSent(error: unknown, requestSent: boolean): AssistantTransportError {
  const transportError = error instanceof Error ? error as AssistantTransportError : new Error(String(error)) as AssistantTransportError;
  transportError.assistantRequestSent = requestSent;
  return transportError;
}

function wasAssistantRequestSent(error: unknown): boolean {
  return Boolean((error as AssistantTransportError | undefined)?.assistantRequestSent);
}

export const useAssistantStore = defineStore("assistant", {
  state: () => ({
    sessionId: null as number | null,
    messages: [] as AssistantMessage[],
    lastAssistantActions: [] as AssistantAction[],
    assistantSessions: [] as AssistantSession[],
    assistantProposals: [] as AssistantProposal[],
    assistantSignals: [] as AssistantSignal[],
    assistantMemoryCandidates: [] as AssistantMemoryCandidate[],
    assistantMemory: null as AssistantMemoryRead | null,
    loadingAssistantSessions: false,
    loadingAssistantProposals: false,
    loadingAssistantSignals: false,
    loadingAssistantMemoryCandidates: false,
    creatingAssistantSession: false,
    archivingAssistantSession: false,
    clearingAssistantSession: false,
    proposalActionBusyId: null as number | null,
    memoryCandidateBusyId: null as number | null,
    sending: false,
    assistantSendInFlight: false,
    assistantSendQueue: Promise.resolve() as Promise<void>,
    _cacheTimestamps: {} as Record<string, number>,
  }),
  actions: {
    isCacheValid(key: string): boolean {
      const timestamp = this._cacheTimestamps[key];
      if (!timestamp) return false;
      return Date.now() - timestamp < 30000;
    },

    invalidateCache(key: string) {
      delete this._cacheTimestamps[key];
    },

    buildWebSocketUrl(path: string) {
      const fallbackBase = "http://127.0.0.1:8000/api";
      const base = typeof api.defaults.baseURL === "string" ? api.defaults.baseURL : fallbackBase;
      const httpUrl = new URL(base, typeof window !== "undefined" ? window.location.origin : undefined);
      const wsProtocol = httpUrl.protocol === "https:" ? "wss:" : "ws:";
      return `${wsProtocol}//${httpUrl.host}${path}`;
    },

    upsertAssistantSession(session: AssistantSession) {
      const next = [...this.assistantSessions];
      const index = next.findIndex((item) => item.id === session.id);
      if (index >= 0) {
        next[index] = { ...next[index], ...session };
      } else {
        next.unshift(session);
      }
      this.assistantSessions = next;
    },

    upsertAssistantProposal(proposal: AssistantProposal) {
      const next = [...this.assistantProposals];
      const index = next.findIndex((item) => item.id === proposal.id);
      if (index >= 0) {
        next[index] = { ...next[index], ...proposal };
      } else {
        next.unshift(proposal);
      }
      this.assistantProposals = next.sort((left, right) => {
        const leftTime = Date.parse(left.updated_at ?? left.created_at ?? "") || 0;
        const rightTime = Date.parse(right.updated_at ?? right.created_at ?? "") || 0;
        return rightTime - leftTime;
      });
    },

    upsertAssistantMemoryCandidate(candidate: AssistantMemoryCandidate) {
      if (candidate.status !== "proposed") {
        this.assistantMemoryCandidates = this.assistantMemoryCandidates.filter((item) => item.id !== candidate.id);
        return;
      }
      const next = [...this.assistantMemoryCandidates];
      const index = next.findIndex((item) => item.id === candidate.id);
      if (index >= 0) {
        next[index] = { ...next[index], ...candidate };
      } else {
        next.unshift(candidate);
      }
      this.assistantMemoryCandidates = next.sort((left, right) => {
        const leftTime = Date.parse(left.updated_at ?? left.created_at ?? "") || 0;
        const rightTime = Date.parse(right.updated_at ?? right.created_at ?? "") || 0;
        return rightTime - leftTime;
      });
    },

    async fetchAssistantSessions() {
      this.loadingAssistantSessions = true;
      try {
        const response = await api.get<{ items: AssistantSession[]; total: number }>("/assistant/sessions");
        this.assistantSessions = response.data.items;
      } finally {
        this.loadingAssistantSessions = false;
      }
    },

    async fetchCurrentAssistantSession() {
      try {
        const response = await api.get<{
          session: AssistantSession;
          inbox: AssistantInbox;
        }>("/assistant/current", {
          params: { include_inbox: false },
        });
        this.sessionId = response.data.session.id;
        this.messages = response.data.session.messages ?? [];
        this.upsertAssistantSession({
          ...response.data.session,
          messages: undefined,
        });
      } catch (error) {
        console.error("Failed to fetch current assistant session:", error);
      }
    },

    async fetchAssistantProposals(statuses = ACTIVE_PROPOSAL_STATUSES) {
      this.loadingAssistantProposals = true;
      try {
        const params = new URLSearchParams();
        statuses.forEach((status) => params.append("status", status));
        params.set("limit", "20");
        const response = await api.get<{ items: AssistantProposal[]; total: number }>("/assistant/proposals", {
          params,
        });
        this.assistantProposals = response.data.items.filter(
          (proposal) => proposal.session_id == null || proposal.session_id === this.sessionId,
        );
      } catch (error) {
        console.error("Failed to fetch assistant proposals:", error);
      } finally {
        this.loadingAssistantProposals = false;
      }
    },

    async fetchAssistantSignals(statuses = ACTIVE_SIGNAL_STATUSES) {
      this.loadingAssistantSignals = true;
      try {
        const params = new URLSearchParams();
        statuses.forEach((status) => params.append("status", status));
        params.set("limit", "20");
        params.set("_ts", String(Date.now()));
        const response = await api.get<{ items: AssistantSignal[]; total: number }>("/assistant/signals", {
          params,
        });
        this.assistantSignals = response.data.items;
      } catch (error) {
        console.error("Failed to fetch assistant signals:", error);
      } finally {
        this.loadingAssistantSignals = false;
      }
    },

    async fetchAssistantMemoryCandidates(statuses = ACTIVE_MEMORY_CANDIDATE_STATUSES) {
      this.loadingAssistantMemoryCandidates = true;
      try {
        const params = new URLSearchParams();
        statuses.forEach((status) => params.append("status", status));
        params.set("limit", "20");
        params.set("_ts", String(Date.now()));
        const response = await api.get<{ items: AssistantMemoryCandidate[]; total: number }>(
          "/assistant/memory/candidates",
          { params },
        );
        this.assistantMemoryCandidates = response.data.items;
      } catch (error) {
        console.error("Failed to fetch assistant memory candidates:", error);
      } finally {
        this.loadingAssistantMemoryCandidates = false;
      }
    },

    async fetchAssistantMemory() {
      try {
        const response = await api.get<AssistantMemoryRead>("/assistant/memory", {
          params: { _ts: Date.now() },
        });
        this.assistantMemory = response.data;
      } catch (error) {
        console.error("Failed to fetch assistant memory:", error);
      }
    },

    async confirmAssistantMemoryCandidate(candidateId: number) {
      this.memoryCandidateBusyId = candidateId;
      try {
        const response = await api.post<AssistantMemoryCandidate>(
          `/assistant/memory/candidates/${candidateId}/confirm`,
        );
        this.upsertAssistantMemoryCandidate(response.data);
        await Promise.allSettled([
          this.fetchAssistantMemoryCandidates(),
          this.fetchAssistantMemory(),
        ]);
        return response.data;
      } finally {
        this.memoryCandidateBusyId = null;
      }
    },

    async rejectAssistantMemoryCandidate(candidateId: number) {
      this.memoryCandidateBusyId = candidateId;
      try {
        const response = await api.post<AssistantMemoryCandidate>(
          `/assistant/memory/candidates/${candidateId}/reject`,
        );
        this.upsertAssistantMemoryCandidate(response.data);
        await this.fetchAssistantMemoryCandidates();
        return response.data;
      } finally {
        this.memoryCandidateBusyId = null;
      }
    },

    async confirmAssistantProposal(proposalId: number, optionId: string) {
      this.proposalActionBusyId = proposalId;
      try {
        const response = await api.post<AssistantProposal>(`/assistant/proposals/${proposalId}/confirm`, {
          option_id: optionId,
        });
        this.upsertAssistantProposal(response.data);
        await this.fetchAssistantProposals();
        return response.data;
      } finally {
        this.proposalActionBusyId = null;
      }
    },

    async rejectAssistantProposal(proposalId: number) {
      this.proposalActionBusyId = proposalId;
      try {
        const response = await api.post<AssistantProposal>(`/assistant/proposals/${proposalId}/reject`);
        this.upsertAssistantProposal(response.data);
        await this.fetchAssistantProposals();
        return response.data;
      } finally {
        this.proposalActionBusyId = null;
      }
    },

    async reviseAssistantProposal(proposalId: number, message: string) {
      this.proposalActionBusyId = proposalId;
      try {
        const response = await api.post<AssistantProposal>(`/assistant/proposals/${proposalId}/revise`, {
          message,
        });
        this.upsertAssistantProposal(response.data);
        await this.fetchAssistantProposals();
        return response.data;
      } finally {
        this.proposalActionBusyId = null;
      }
    },

    async retryAssistantProposal(proposalId: number) {
      this.proposalActionBusyId = proposalId;
      try {
        const response = await api.post<AssistantProposal>(`/assistant/proposals/${proposalId}/retry`);
        this.upsertAssistantProposal(response.data);
        await this.fetchAssistantProposals();
        return response.data;
      } finally {
        this.proposalActionBusyId = null;
      }
    },

    async fetchSession(sessionId: number) {
      try {
        const response = await api.get<AssistantSession>(`/assistant/sessions/${sessionId}`);
        this.sessionId = response.data.id;
        this.messages = response.data.messages ?? [];
        this.upsertAssistantSession({
          ...response.data,
          messages: undefined,
        });
      } catch (error) {
        console.error("Failed to fetch session:", error);
      }
    },

    async createAssistantSession(title?: string) {
      this.creatingAssistantSession = true;
      try {
        const response = await api.post<AssistantSession>("/assistant/sessions", { title });
        this.sessionId = response.data.id;
        this.messages = response.data.messages ?? [];
        this.upsertAssistantSession({
          ...response.data,
          messages: undefined,
        });
        this.lastAssistantActions = [];
      } catch (error) {
        throw error;
      } finally {
        this.creatingAssistantSession = false;
      }
    },

    async switchAssistantSession(sessionId: number) {
      try {
        await this.fetchSession(sessionId);
      } catch (error) {
        throw error;
      }
    },

    async archiveCurrentAssistantSession() {
      if (this.sessionId == null) return;
      this.archivingAssistantSession = true;
      try {
        await api.post(`/assistant/sessions/${this.sessionId}/archive`);
        this.assistantSessions = this.assistantSessions.filter((item) => item.id !== this.sessionId);
        await Promise.all([this.fetchAssistantSessions(), this.fetchCurrentAssistantSession()]);
      } catch (error) {
        throw error;
      } finally {
        this.archivingAssistantSession = false;
      }
    },

    async clearCurrentAssistantSession() {
      if (this.sessionId == null) return;
      this.clearingAssistantSession = true;
      try {
        await api.delete(`/assistant/sessions/${this.sessionId}/messages`);
        this.messages = [];
        this.lastAssistantActions = [];
        await this.fetchAssistantSessions();
      } catch (error) {
        throw error;
      } finally {
        this.clearingAssistantSession = false;
      }
    },

    async sendAssistantMessageStream(message: string, onRefresh?: () => Promise<void>) {
      const parsedMessage = await defaultInputAdapter.parse(message);
      const normalizedMessage = parsedMessage.trim();
      if (!normalizedMessage) return;

      this.sending = true;
      let requestSent = false;
      const userMessageId = `local-${Date.now()}`;
      const assistantMsgId = `assistant-stream-${Date.now()}`;
      this.messages.push({ id: userMessageId, role: "user", content: normalizedMessage });
      this.messages.push({ id: assistantMsgId, role: "assistant", content: "" });
      this.lastAssistantActions = [];

      let completed = false;
      try {
        await new Promise<void>((resolve, reject) => {
          let finished = false;
          const ws = new WebSocket(this.buildWebSocketUrl("/ws/assistant?user_id=local-user"));

          const rejectOnce = (error: unknown) => {
            if (finished) return;
            finished = true;
            try { ws.close(); } catch { /* ignore */ }
            reject(error);
          };

          ws.onopen = () => {
            ws.send(JSON.stringify({ message: normalizedMessage, session_id: this.sessionId }));
            requestSent = true;
          };

          ws.onmessage = (event) => {
            void (async () => {
              const data = JSON.parse(event.data) as {
                type: string;
                text?: string;
                actions?: AssistantAction[];
                session_id?: number;
                full_reply?: string;
              };
              const assistantMessage = this.messages.find((item) => item.id === assistantMsgId);

              if (data.type === "token") {
                if (assistantMessage) assistantMessage.content += data.text ?? "";
                return;
              }
              if (data.type === "actions") {
                this.lastAssistantActions = data.actions ?? [];
                return;
              }
              if (data.type === "done") {
                finished = true;
                this.sessionId = data.session_id ?? this.sessionId;
                const rendered = await defaultOutputAdapter.render(data.full_reply ?? "");
                if (assistantMessage) assistantMessage.content = rendered;
                ws.close();
                completed = true;
                await this.refreshAssistantSidebarsAfterSend();
                if (onRefresh) await onRefresh();
                resolve();
                return;
              }
              if (data.type === "error") {
                rejectOnce(new Error(data.text || "Assistant WebSocket failed."));
              }
            })().catch(rejectOnce);
          };

          ws.onerror = () => rejectOnce(new Error("Assistant WebSocket connection failed."));
          ws.onclose = () => { if (!finished) rejectOnce(new Error("Assistant WebSocket closed unexpectedly.")); };
        });
      } catch (error) {
        this.messages = this.messages.filter((item) => item.id !== userMessageId && item.id !== assistantMsgId);
        this.lastAssistantActions = [];
        this.sending = false;
        throw markAssistantRequestSent(error, requestSent);
      } finally {
        if (!completed) this.sending = false;
      }
    },

    async sendAssistantMessage(message: string, onRefresh?: () => Promise<void>) {
      const previousSend = this.assistantSendQueue;
      let releaseQueuedSend: (() => void) | null = null;
      this.assistantSendQueue = new Promise<void>((resolve) => {
        releaseQueuedSend = resolve;
      });
      await previousSend.catch(() => {});
      await new Promise((resolve) => window.setTimeout(resolve, SEND_QUEUE_DELAY_MS));
      this.assistantSendInFlight = true;
      try {
        try {
          await this.sendAssistantMessageStream(message, onRefresh);
          return;
        } catch (error) {
          if (wasAssistantRequestSent(error)) {
            console.error("Assistant WebSocket failed after request was sent:", error);
            await Promise.allSettled([
              this.fetchCurrentAssistantSession(),
              this.refreshAssistantSidebarsAfterSend(),
            ]);
            this.messages.push({
              id: `assistant-error-${Date.now()}`,
              role: "assistant",
              content: "连接中断：这次请求已经送达后端，我不会改用备用通道重复提交。已刷新当前状态，请稍后查看结果或重新发送新的请求。",
            });
            this.lastAssistantActions = [];
            return;
          }
          // Fallback to REST only when the WebSocket request never left the browser.
        }

        const parsedMessage = await defaultInputAdapter.parse(message);
        const normalizedMessage = parsedMessage.trim();
        if (!normalizedMessage) return;

        this.sending = true;
        this.messages.push({ id: `local-${Date.now()}`, role: "user", content: normalizedMessage });

        try {
          const response = await api.post<{
            session_id: number;
            reply: string;
            actions: AssistantAction[];
          }>("/assistant/message", {
            session_id: this.sessionId,
            message: normalizedMessage,
          });

          this.sessionId = response.data.session_id;
          const renderedReply = await defaultOutputAdapter.render(response.data.reply);
          this.messages.push({
            id: `assistant-${Date.now()}`,
            role: "assistant",
            content: renderedReply,
            tool_calls_json: response.data.actions,
          });
          this.lastAssistantActions = response.data.actions;

          await this.refreshAssistantSidebarsAfterSend();
          if (onRefresh) await onRefresh();
        } catch (error) {
          console.error("Assistant message send failed:", error);
          this.messages.push({
            id: `assistant-error-${Date.now()}`,
            role: "assistant",
            content: "发送失败：网络连接不可用或服务暂时不可达。请恢复连接后重试，我不会重复执行这次未送达的请求。",
          });
          this.lastAssistantActions = [];
        } finally {
          this.sending = false;
        }
      } finally {
        this.assistantSendInFlight = false;
        this.sending = false;
        releaseQueuedSend?.();
      }
    },

    async refreshAssistantSidebarsAfterSend() {
      await Promise.allSettled([
        this.fetchAssistantProposals(),
        this.fetchAssistantSignals(),
        this.fetchAssistantMemoryCandidates(),
      ]);
    },
  },
});
