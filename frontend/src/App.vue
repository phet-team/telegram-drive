<template>
  <div class="h-screen h-[100dvh] w-full max-w-[100vw] overflow-hidden bg-drive-bg text-gray-900 font-sans">
    <router-view />
  </div>
</template>

<script setup>
import { watch } from 'vue';
import { useAuthStore } from './stores/auth';
import { useStorageStore } from './stores/storage';

const auth = useAuthStore();
const storage = useStorageStore();

// Once auth is initialized (or the user logs in), load the per-user storage
// state; the store keeps polling from then on. Cleared on logout.
watch(
  () => auth.isAuthenticated,
  (authed) => {
    if (authed) {
      storage.fetchMyStorage().catch(() => {});
    } else {
      storage.myStorage = null;
      storage.stopPolling();
    }
  },
  { immediate: true }
);
</script>
