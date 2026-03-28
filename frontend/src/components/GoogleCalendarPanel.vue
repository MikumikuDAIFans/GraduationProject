<script setup lang="ts">
import type { GoogleCalendarStatus, GoogleCalendarSyncResult } from "@/stores/workspace";

defineProps<{
  status: GoogleCalendarStatus | null;
  syncResult: GoogleCalendarSyncResult | null;
  feedback: string | null;
  startingAuth: boolean;
  syncing: boolean;
}>();

defineEmits<{
  connect: [];
  sync: [];
  dismissFeedback: [];
}>();

function toneForStatus(status: string | undefined) {
  if (status === "synced") return "bg-positive-light text-positive border-positive/20";
  if (status === "connected") return "bg-sky-50 text-sky-700 border-sky-200";
  if (status === "error") return "bg-danger-light text-danger border-danger/20";
  return "bg-slate-100 text-slate-500 border-slate-200";
}

function labelForStatus(status: string | undefined) {
  if (status === "synced") return "Synced";
  if (status === "connected") return "Connected";
  if (status === "error") return "Error";
  return "Disconnected";
}
</script>

<template>
  <section class="rounded-2xl border border-white/70 bg-white/70 px-5 py-4 shadow-panel backdrop-blur-xl">
    <div class="flex flex-wrap items-center gap-3">
      <!-- Icon + label -->
      <div class="flex items-center gap-2.5 flex-1 min-w-0">
        <svg class="h-5 w-5 shrink-0 text-slate-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/>
          <line x1="16" y1="2" x2="16" y2="6"/>
          <line x1="8" y1="2" x2="8" y2="6"/>
          <line x1="3" y1="10" x2="21" y2="10"/>
        </svg>
        <div class="min-w-0">
          <p class="text-xs font-semibold uppercase tracking-[0.22em] text-slate-400">Google Calendar</p>
          <div class="mt-0.5 flex items-center gap-2">
            <span
              class="inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-semibold uppercase tracking-[0.15em]"
              :class="toneForStatus(status?.status)"
            >
              {{ labelForStatus(status?.status) }}
            </span>
            <span v-if="status?.last_sync_at" class="truncate text-xs text-slate-400">
              Last sync {{ status.last_sync_at }}
            </span>
          </div>
        </div>
      </div>

      <!-- Sync result mini pills -->
      <div v-if="syncResult" class="hidden items-center gap-2 sm:flex">
        <span class="rounded-lg bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-600">↑ {{ syncResult.pushed }} pushed</span>
        <span class="rounded-lg bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-600">↓ {{ syncResult.imported }} imported</span>
      </div>

      <!-- Action buttons -->
      <div class="flex shrink-0 items-center gap-2">
        <button
          type="button"
          class="rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-600 transition hover:border-accent/30 hover:bg-accent-light hover:text-accent disabled:cursor-not-allowed disabled:opacity-50"
          :disabled="startingAuth"
          @click="$emit('connect')"
        >
          {{ startingAuth ? "Redirecting…" : status?.connected ? "Reconnect" : "Connect" }}
        </button>
        <button
          type="button"
          class="rounded-xl bg-accent px-3 py-2 text-xs font-semibold text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
          :disabled="syncing || !status?.connected"
          @click="$emit('sync')"
        >
          {{ syncing ? "Syncing…" : "Sync now" }}
        </button>
      </div>
    </div>

    <!-- Feedback / error -->
    <div v-if="feedback || status?.last_error" class="mt-3 flex items-start justify-between gap-3">
      <p
        class="rounded-xl px-3 py-2 text-xs leading-5"
        :class="status?.last_error ? 'bg-danger-light text-danger' : 'bg-slate-100 text-slate-600'"
      >
        {{ status?.last_error || feedback }}
      </p>
      <button
        v-if="feedback"
        type="button"
        class="shrink-0 text-xs font-semibold text-slate-400 hover:text-slate-600"
        @click="$emit('dismissFeedback')"
      >
        Dismiss
      </button>
    </div>
  </section>
</template>
