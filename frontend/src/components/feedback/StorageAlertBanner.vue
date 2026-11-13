<template>
  <div
    v-if="isDown"
    class="shrink-0 flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2.5 bg-[#c5221f] text-white text-sm select-none"
    role="alert"
  >
    <AlertTriangle class="w-4 h-4 shrink-0" />
    <span class="font-medium">Storage is down.</span>
    <span class="min-w-0 truncate">{{ reasonLabel(reason) }}.</span>
    <router-link
      to="/settings/storage"
      class="ml-auto shrink-0 px-3.5 py-1 rounded-full bg-white text-[#c5221f] text-xs font-medium hover:bg-red-50"
    >
      Reconnect
    </router-link>
  </div>

  <div
    v-if="isUserAlert"
    class="shrink-0 flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2.5 bg-[#e37400] text-white text-sm select-none"
    role="alert"
  >
    <AlertTriangle class="w-4 h-4 shrink-0" />
    <span class="font-medium">{{ userAlertTitle }}</span>
    <span v-if="userAlertDetail" class="min-w-0 truncate">{{ userAlertDetail }}</span>
    <router-link
      to="/settings/my-storage"
      class="ml-auto shrink-0 px-3.5 py-1 rounded-full bg-white text-[#b06000] text-xs font-medium hover:bg-orange-50"
    >
      Fix
    </router-link>
  </div>
</template>

<script setup>
import { ref, computed, watch, onUnmounted } from 'vue';
import { AlertTriangle } from 'lucide-vue-next';
import { useAuthStore } from '../../stores/auth';
import { useStorageStore } from '../../stores/storage';
import { getStorageSettings, reasonLabel } from '../../services/storage';

const POLL_MS = 60000;

const auth = useAuthStore();
const storageStore = useStorageStore();
const state = ref('ok');
const reason = ref('');
let timer = null;

const isSuperuser = computed(() => !!auth.user?.is_superuser);
const isDown = computed(() => isSuperuser.value && state.value === 'down');
const isUserAlert = computed(() => storageStore.isOwnDown || storageStore.isOwnDisconnectedWithFiles);
const userAlertTitle = computed(() =>
  storageStore.isOwnDown ? 'Your Telegram storage is not working.' : 'Your Telegram account is disconnected.'
);
const userAlertDetail = computed(() =>
  storageStore.isOwnDown
    ? `${reasonLabel(storageStore.own.reason)}.`
    : 'Files stored in it are unavailable until you reconnect the same account.'
);

const poll = async () => {
  try {
    const { data } = await getStorageSettings();
    state.value = data.status.alert_state;
    reason.value = data.status.last_check_reason;
  } catch (err) {
    // The banner is advisory: a failed poll keeps the last known state and retries next minute.
    console.warn('Storage status poll failed:', err?.response?.status || err?.message);
  }
};

const stop = () => {
  if (timer) clearInterval(timer);
  timer = null;
};

watch(
  isSuperuser,
  (value) => {
    stop();
    if (value) {
      poll();
      timer = setInterval(poll, POLL_MS);
    }
  },
  { immediate: true }
);

onUnmounted(stop);
</script>
