import { defineStore } from "pinia";
import { api } from "@/api/client";
import { defaultInputAdapter } from "@/inputAdapters/textInput";
import { defaultOutputAdapter } from "@/outputAdapters/textOutput";
import { i18n } from "@/i18n";

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
  messages: AssistantMessage[];
}

export const useAssistantStore = defineStore("assistant", {
  state: () => ({
    sessionId: null as number | null,
    messages: [] as AssistantMessage[],
    lastAssistantActions: [] as AssistantAction[],
    assistantInbox: [] as AssistantInboxItem[],
    assistantInboxUnreadTotal: 0,
    assistantSummary: null as AssistantSummary | null,
    assistantSessions: [] as AssistantSession[],
    loadingAssistantSessions: false,
    creatingAssistantSession: false,
    archivingAssistantSession: false,
    clearingAssistantSession: false,
    sending: false,
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

    async fetchAssistantInbox() {
      try {
        const response = await api.get<AssistantInbox>("/assistant/inbox");
        this.assistantInbox = response.data.items;
        this.assistantInboxUnreadTotal = response.data.unread_total;
      } catch (error) {
        console.error("Failed to fetch assistant inbox:", error);
      }
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
        }>("/assistant/current");
        this.sessionId = response.data.session.id;
        this.messages = response.data.session.messages;
        this.assistantInbox = response.data.inbox.items;
        this.assistantInboxUnreadTotal = response.data.inbox.unread_total;
        const existing = this.assistantSessions.find((item) => item.id === response.data.session.id);
        if (!existing) {
          this.assistantSessions = [response.data.session, ...this.assistantSessions];
        }
      } catch (error) {
        console.error("Failed to fetch current assistant session:", error);
      }
    },

    async fetchAssistantSummary() {
      try {
        const response = await api.get<AssistantSummary>("/assistant/summary");
        this.assistantSummary = response.data;
      } catch (error) {
        console.error("Failed to fetch assistant summary:", error);
      }
    },

    async fetchSession(sessionId: number) {
      try {
        const response = await api.get<AssistantSession>(`/assistant/sessions/${sessionId}`);
        this.sessionId = response.data.id;
        this.messages = response.data.messages;
        this.assistantSessions = this.assistantSessions.map((item) =>
          item.id === response.data.id ? response.data : item,
        );
      } catch (error) {
        console.error("Failed to fetch session:", error);
      }
    },

    async createAssistantSession(title?: string) {
      this.creatingAssistantSession = true;
      try {
        const response = await api.post<AssistantSession>("/assistant/sessions", { title });
        this.sessionId = response.data.id;
        this.messages = response.data.messages;
        this.assistantSessions = [response.data, ...this.assistantSessions.filter((item) => item.id !== response.data.id)];
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

    async updateInboxItem(itemId: string, action: "read" | "archive") {
      try {
        await api.post("/assistant/inbox/" + itemId, null, { params: { action } });
        await this.fetchCurrentAssistantSession();
      } catch (error) {
        console.error("Failed to update inbox item:", error);
        throw error;
      }
    },

    async sendAssistantMessageStream(message: string, onRefresh?: () => Promise<void>) {
      const parsedMessage = await defaultInputAdapter.parse(message);
      const normalizedMessage = parsedMessage.trim();
      if (!normalizedMessage) return;

      this.sending = true;
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
                this.sending = false;
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
        throw error;
      } finally {
        if (!completed) this.sending = false;
      }
    },

    async sendAssistantMessage(message: string, onRefresh?: () => Promise<void>) {
      try {
        await this.sendAssistantMessageStream(message, onRefresh);
        return;
      } catch {
        // Fallback to REST
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

        if (onRefresh) await onRefresh();
      } catch (error) {
        throw error;
      } finally {
        this.sending = false;
      }
    },
  },
});
