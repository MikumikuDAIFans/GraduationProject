<script setup lang="ts">
import type { GoogleCalendarStatus, GoogleCalendarSyncResult } from "@/stores/workspace";

defineProps<{
  status: GoogleCalendarStatus | null;
  syncResult: GoogleCalendarSyncResult | null;
  feedback: string | null;
  startingAuth: boolean;
  syncing: boolean;
}>();

defineEmits<{ connect: []; sync: []; dismissFeedback: [] }>();

function statusBadge(s: string | undefined) {
  if (s === "synced")     return { cls: "bg-positive-light text-positive",   label: "Synced" };
  if (s === "connected")  return { cls: "bg-accent-light text-accent",       label: "Connected" };
  if (s === "error")      return { cls: "bg-danger-light text-danger",       label: "Error" };
  return                         { cls: "bg-surface-3 text-ink-3",           label: "Disconnected" };
}
</script>

<template>
  <div class="flex flex-wrap items-center gap-3 rounded-xl border border-border bg-white px-4 py-3 shadow-card">
    <!-- Icon + status -->
    <div class="flex min-w-0 flex-1 items-center gap-3">
      <svg class="h-4 w-4 shrink-0 text-ink-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
        <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/>
        <line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/>
        <line x1="3" y1="10" x2="21" y2="10"/>
      </svg>
      <div class="min-w-0">
        <p class="text-xs font-semibold text-ink-2">Google Calendar</p>
        <div class="mt-0.5 flex items-center gap-2">
          <span class="rounded-md px-1.5 py-0.5 text-[10px] font-bold" :class="statusBadge(status?.status).cls">
            {{ statusBadge(status?.status).label }}
          </span>
          <span v-if="status?.last_sync_at" class="truncate text-[11px] text-ink-3">{{ status.last_sync_at }}</span>
        </div>
      </div>
    </div>

    <!-- Sync stats -->
    <div v-if="syncResult" class="hidden items-center gap-2 sm:flex">
      <span class="rounded-md bg-surface-3 px-2 py-0.5 text-[11px] font-medium text-ink-3">↑ {{ syncResult.pushed }}</span>
      <span class="rounded-md bg-surface-3 px-2 py-0.5 text-[11px] font-medium text-ink-3">↓ {{ syncResult.imported }}</span>
    </div>

    <!-- Buttons -->
    <div class="flex shrink-0 gap-2">
      <button
        type="button"
        class="rounded-lg border border-border bg-surface px-3 py-1.5 text-xs font-medium text-ink-2 transition hover:bg-surface-3 disabled:cursor-not-allowed disabled:opacity-50"
        :disabled="startingAuth"
        @click="$emit('connect')"
      >{{ startingAuth ? "Redirecting…" : status?.connected ? "Reconnect" : "Connect" }}</button>
      <button
        type="button"
        class="rounded-lg bg-accent px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-50"
        :disabled="syncing || !status?.connected"
        @click="$emit('sync')"
      >{{ syncing ? "Syncing…" : "Sync" }}</button>
    </div>

    <!-- Feedback -->
    <div v-if="feedback || status?.last_error" class="w-full">
      <div class="flex items-center justify-between gap-3 rounded-lg px-3 py-2 text-xs"
        :class="status?.last_error ? 'bg-danger-light text-danger' : 'bg-surface-3 text-ink-3'">
        <span>{{ status?.last_error || feedback }}</span>
        <button v-if="feedback" type="button" class="font-semibold hover:opacity-70" @click="$emit('dismissFeedback')">✕</button>
      </div>
    </div>
  </div>
</template>
