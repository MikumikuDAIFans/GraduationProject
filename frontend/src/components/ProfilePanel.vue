<script setup lang="ts">
import { reactive, watch } from "vue";
import type { UserProfile } from "@/stores/workspace";

const props = defineProps<{ profile: UserProfile | null; saving: boolean }>();
const emit = defineEmits<{ save: [payload: Partial<UserProfile>] }>();

const form = reactive({
  display_name: "",
  home_location_name: "",
  work_location_name: "",
  transport_preference: "driving",
  wake_up_time: "",
  sleep_time: "",
});

watch(() => props.profile, (p) => {
  form.display_name        = p?.display_name ?? "";
  form.home_location_name  = p?.home_location_name ?? "";
  form.work_location_name  = p?.work_location_name ?? "";
  form.transport_preference= p?.transport_preference ?? "driving";
  form.wake_up_time        = p?.wake_up_time ?? "";
  form.sleep_time          = p?.sleep_time ?? "";
}, { immediate: true });

function save() {
  emit("save", {
    display_name:         form.display_name || null,
    home_location_name:   form.home_location_name || null,
    work_location_name:   form.work_location_name || null,
    transport_preference: form.transport_preference || null,
    wake_up_time:         form.wake_up_time || null,
    sleep_time:           form.sleep_time || null,
  });
}

const inputCls = "w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-ink placeholder:text-ink-3 transition focus:border-accent/50 focus:outline-none focus:ring-2 focus:ring-accent/10";
const labelCls = "mb-1 block text-xs font-medium text-ink-3";
</script>

<template>
  <div>
    <p class="mb-3 text-xs font-bold uppercase tracking-widest text-ink-3">Profile Settings</p>
    <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      <label class="block">
        <span :class="labelCls">Display name</span>
        <input v-model="form.display_name" :class="inputCls" placeholder="Your name" />
      </label>
      <label class="block">
        <span :class="labelCls">Transport</span>
        <select v-model="form.transport_preference" :class="inputCls">
          <option value="driving">Driving</option>
          <option value="walking">Walking</option>
        </select>
      </label>
      <label class="block">
        <span :class="labelCls">Home location</span>
        <input v-model="form.home_location_name" :class="inputCls" placeholder="e.g. 北京市朝阳区" />
      </label>
      <label class="block">
        <span :class="labelCls">Work location</span>
        <input v-model="form.work_location_name" :class="inputCls" placeholder="e.g. 北京市海淀区" />
      </label>
      <label class="block">
        <span :class="labelCls">Wake up</span>
        <input v-model="form.wake_up_time" :class="inputCls" placeholder="07:30" />
      </label>
      <label class="block">
        <span :class="labelCls">Sleep</span>
        <input v-model="form.sleep_time" :class="inputCls" placeholder="23:30" />
      </label>
    </div>
    <div class="mt-4 flex justify-end">
      <button
        type="button"
        class="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-white transition hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-50"
        :disabled="saving"
        @click="save"
      >{{ saving ? "Saving…" : "Save profile" }}</button>
    </div>
  </div>
</template>
