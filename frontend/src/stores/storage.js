import { defineStore } from 'pinia';
import { ref, computed, onScopeDispose } from 'vue';
import { getMyStorage } from '../services/storage';

const POLL_MS = 60000;

export const useStorageStore = defineStore('storage', () => {
  const myStorage = ref(null);
  const loading = ref(false);
  const error = ref('');
  const isInitialized = ref(false);
  let timer = null;

  const canUpload = computed(() => (myStorage.value ? myStorage.value.can_upload : true));
  const uploadTarget = computed(() => myStorage.value?.upload_target || 'own');
  const effectiveTarget = computed(() => myStorage.value?.effective_target || null);
  const systemAllowed = computed(() => !!myStorage.value?.system_allowed);
  const own = computed(() => myStorage.value?.own || {});
  const isOwnDown = computed(() => myStorage.value?.own?.status === 'down');
  const isOwnDisconnectedWithFiles = computed(
    () => myStorage.value?.own?.connected === false && (myStorage.value?.own?.file_count > 0)
  );

  const fetchMyStorage = async () => {
    loading.value = true;
    error.value = '';
    try {
      const { data } = await getMyStorage();
      myStorage.value = data;
      isInitialized.value = true;
      startPolling();
      return data;
    } catch (err) {
      error.value = err?.response?.status === 401 ? '' : (err?.response?.data?.error || err?.message || 'Could not load storage status');
      throw err;
    } finally {
      loading.value = false;
    }
  };

  const pollIfVisible = () => {
    if (document.visibilityState === 'visible') fetchMyStorage().catch(() => {});
  };

  const onVisibility = () => {
    // Coming back to the tab should refresh the state right away.
    if (document.visibilityState === 'visible' && timer) fetchMyStorage().catch(() => {});
  };

  const startPolling = () => {
    if (timer) return;
    document.addEventListener('visibilitychange', onVisibility);
    timer = setInterval(pollIfVisible, POLL_MS);
  };

  const stopPolling = () => {
    if (timer) clearInterval(timer);
    timer = null;
    document.removeEventListener('visibilitychange', onVisibility);
  };

  onScopeDispose(stopPolling);

  return {
    myStorage,
    loading,
    error,
    isInitialized,
    canUpload,
    uploadTarget,
    effectiveTarget,
    systemAllowed,
    own,
    isOwnDown,
    isOwnDisconnectedWithFiles,
    fetchMyStorage,
    startPolling,
    stopPolling,
  };
});
