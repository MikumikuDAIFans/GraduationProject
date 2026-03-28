<script setup lang="ts">
import { reactive, watch } from "vue";
import type { UserProfile } from "@/stores/workspace";

const props = defineProps<{
  profile: UserProfile | null;
  saving: boolean;
}>();

const emit = defineEmits<{
  save: [payload: Partial<UserProfile>];
}>();

const form = reactive({
  display_name: "",
  home_location_name: "",
  work_location_name: "",
  transport_preference: "driving",
  wake_up_time: "",
  sleep_time: "",
});

watch(
  () => props.profile,
  (profile) => {
    form.display_name = profile?.display_name ?? "";
    form.home_location_name = profile?.home_location_name ?? "";
    form.work_location_name = profile?.work_location_name ?? "";
    form.transport_preference = profile?.transport_preference ?? "driving";
    form.wake_up_time = profile?.wake_up_time ?? "";
    form.sleep_time = profile?.sleep_time ?? "";
  },
  { immediate: true },
);

function save() {
  emit("save", {
    display_name: form.display_name || null,
    home_location_name: form.home_location_name || null,
    work_location_name: form.work_location_name || null,
    transport_preference: form.transport_preference || null,
    wake_up_time: form.wake_up_time || null,
    sleep_time: form.sleep_time || null,
  });
}
</script>

<template>
  <section class="rounded-2xl border border-white/70 bg-white/70 px-5 py-4 shadow-panel backdrop-blur-xl">
    <p class="mb-4 text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">Profile Settings</p>
    <div class="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
      <label class="block">
        <span class="mb-1 block text-xs font-semibold text-slate-500">Display name</span>
        <input
          v-model="form.display_name"
          class="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-ink transition focus:border-accent/50 focus:outline-none focus:ring-2 focus:ring-accent/10"
          placeholder="Your name"
        />
      </label>
      <label class="block">
        <span class="mb-1 block text-xs font-semibold text-slate-500">Transport</span>
        <select
          v-model="form.transport_preference"
          class="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-ink transition focus:border-accent/50 focus:outline-none focus:ring-2 focus:ring-accent/10"
        >
          <option value="driving">Driving</option>
          <option value="walking">Walking</option>
        </select>
      </label>
      <label class="block">
        <span class="mb-1 block text-xs font-semibold text-slate-500">Home location</span>
        <input
          v-model="form.home_location_name"
          class="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-ink transition focus:border-accent/50 focus:outline-none focus:ring-2 focus:ring-accent/10"
          placeholder="e.g. 北京市朝阳区"
        />
      </label>
      <label class="block">
        <span class="mb-1 block text-xs font-semibold text-slate-500">Work location</span>
        <input
          v-model="form.work_location_name"
          class="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-ink transition focus:border-accent/50 focus:outline-none focus:ring-2 focus:ring-accent/10"
          placeholder="e.g. 北京市海淀区"
        />
      </label>
      <label class="block">
        <span class="mb-1 block text-xs font-semibold text-slate-500">Wake up</span>
        <input
          v-model="form.wake_up_time"
          class="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-ink transition focus:border-accent/50 focus:outline-none focus:ring-2 focus:ring-accent/10"
          placeholder="07:30"
        />
      </label>
      <label class="block">
        <span class="mb-1 block text-xs font-semibold text-slate-500">Sleep</span>
        <input
          v-model="form.sleep_time"
          class="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-ink transition focus:border-accent/50 focus:outline-none focus:ring-2 focus:ring-accent/10"
          placeholder="23:30"
        />
      </label>
    </div>
    <div class="mt-4 flex justify-end">
      <button
        type="button"
        class="rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
        :disabled="saving"
        @click="save"
      >
        {{ saving ? "Saving…" : "Save profile" }}
      </button>
    </div>
  </section>
</template>
