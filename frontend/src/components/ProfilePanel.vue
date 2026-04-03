<script setup lang="ts">
import { computed, reactive, watch } from "vue";
import { useI18n } from "vue-i18n";
import type { UserProfile } from "@/stores/workspace";

const props = defineProps<{ profile: UserProfile | null; saving: boolean }>();
const emit = defineEmits<{ save: [payload: Partial<UserProfile>] }>();
const { t } = useI18n();

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

function isValidTime(value: string) {
  return !value || /^([01]\d|2[0-3]):([0-5]\d)$/.test(value);
}

const errors = computed(() => {
  const next: Record<string, string> = {};
  if (!isValidTime(form.wake_up_time)) {
    next.wake_up_time = t("profile.invalidTime");
  }
  if (!isValidTime(form.sleep_time)) {
    next.sleep_time = t("profile.invalidTime");
  }
  if (form.wake_up_time && form.sleep_time && form.wake_up_time === form.sleep_time) {
    next.sleep_time = t("profile.invalidSleep");
  }
  return next;
});

const hasErrors = computed(() => Object.keys(errors.value).length > 0);

function save() {
  if (hasErrors.value) {
    return;
  }
  emit("save", {
    display_name: form.display_name || null,
    home_location_name: form.home_location_name || null,
    work_location_name: form.work_location_name || null,
    transport_preference: form.transport_preference || null,
    wake_up_time: form.wake_up_time || null,
    sleep_time: form.sleep_time || null,
  });
}

const inputCls = "w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-ink placeholder:text-ink-3 transition focus:border-accent/50 focus:outline-none focus:ring-2 focus:ring-accent/10";
const labelCls = "mb-1 block text-xs font-medium text-ink-3";
</script>

<template>
  <div>
    <p class="mb-3 text-xs font-bold uppercase tracking-widest text-ink-3">{{ t("profile.title") }}</p>
    <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      <label class="block">
        <span :class="labelCls">{{ t("profile.displayName") }}</span>
        <input v-model="form.display_name" :class="inputCls" :placeholder="t('profile.displayNamePlaceholder')" />
      </label>
      <label class="block">
        <span :class="labelCls">{{ t("profile.transport") }}</span>
        <select v-model="form.transport_preference" :class="inputCls">
          <option value="driving">{{ t("profile.driving") }}</option>
          <option value="walking">{{ t("profile.walking") }}</option>
        </select>
      </label>
      <label class="block">
        <span :class="labelCls">{{ t("profile.homeLocation") }}</span>
        <input v-model="form.home_location_name" :class="inputCls" :placeholder="t('profile.locationPlaceholder')" />
      </label>
      <label class="block">
        <span :class="labelCls">{{ t("profile.workLocation") }}</span>
        <input v-model="form.work_location_name" :class="inputCls" :placeholder="t('profile.locationPlaceholder')" />
      </label>
      <label class="block">
        <span :class="labelCls">{{ t("profile.wakeUp") }}</span>
        <input v-model="form.wake_up_time" :class="inputCls" :placeholder="t('profile.timePlaceholder')" />
        <p v-if="errors.wake_up_time" class="mt-1 text-[11px] text-danger">{{ errors.wake_up_time }}</p>
      </label>
      <label class="block">
        <span :class="labelCls">{{ t("profile.sleep") }}</span>
        <input v-model="form.sleep_time" :class="inputCls" :placeholder="t('profile.timePlaceholder')" />
        <p v-if="errors.sleep_time" class="mt-1 text-[11px] text-danger">{{ errors.sleep_time }}</p>
      </label>
    </div>
    <div class="mt-4 flex justify-end">
      <button
        type="button"
        class="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-white transition hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-50"
        :disabled="saving || hasErrors"
        @click="save"
      >
        {{ saving ? t("common.saving") : t("profile.saveProfile") }}
      </button>
    </div>
  </div>
</template>
