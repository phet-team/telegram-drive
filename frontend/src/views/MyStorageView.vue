<template>
  <div class="min-h-screen bg-drive-bg text-[#1f1f1f]">
    <header class="h-16 flex items-center gap-2 px-3 sm:px-5 bg-drive-bg border-b border-drive-border">
      <button
        type="button"
        class="text-[#444746] hover:text-[#1f1f1f] p-2 rounded-full hover:bg-black/5 transition-colors cursor-pointer"
        title="Back to Drive"
        @click="$router.push('/')"
      >
        <ArrowLeft class="w-5 h-5" />
      </button>
      <Cloud class="w-5 h-5 text-[#0b57d0]" />
      <h1 class="text-[20px] sm:text-[22px] font-normal tracking-tight">My storage</h1>
    </header>

    <main class="max-w-3xl mx-auto p-4 sm:p-6 flex flex-col gap-6">
      <div v-if="isLoading" class="py-16 flex justify-center">
        <div class="animate-spin rounded-full h-7 w-7 border-2 border-[#0b57d0] border-t-transparent"></div>
      </div>

      <div v-else-if="loadError" class="bg-white border border-[#f1b7b2] rounded-2xl px-4 py-3 text-sm text-[#c5221f]">
        {{ loadError }}
      </div>

      <template v-else-if="me">
        <!-- Not connected: consent + wizard -->
        <section v-if="!connected" class="bg-white rounded-3xl border border-gray-150 p-5 shadow-xs">
          <h2 class="text-base font-medium mb-1">Connect your Telegram account</h2>
          <p class="text-xs text-[#747775] mb-4">
            Your own Telegram account is used to store and read your files.
          </p>

          <label v-if="!loginPending" class="flex items-start gap-3 p-4 rounded-2xl bg-[#f8fafd] border border-gray-200 cursor-pointer">
            <input v-model="consent" type="checkbox" :disabled="wizardActive" class="mt-0.5 w-4 h-4 rounded border-gray-300 text-[#0b57d0] focus:ring-[#0b57d0] cursor-pointer disabled:cursor-not-allowed disabled:opacity-50" />
            <span class="text-sm text-[#444746] leading-relaxed">
              The server keeps a login session of your Telegram account so it can store and read your
              files. That session can access your whole Telegram account. We recommend a separate
              Telegram account used only for storage.
            </span>
          </label>

          <div v-if="consent || loginPending" class="mt-4">
            <TelegramLoginWizard ref="wizardRef" :api-base-path="'/storage/me'" @connected="handleConnected" @progress="wizardActive = $event" />
          </div>
        </section>

        <!-- Connected: account status -->
        <section v-else class="bg-white rounded-3xl border border-gray-150 p-5 shadow-xs">
          <div class="flex items-center justify-between gap-3 mb-4">
            <h2 class="text-base font-medium truncate">{{ own.account_name || 'Your Telegram account' }}</h2>
            <span
              :class="[
                'shrink-0 text-[10px] font-semibold px-2 py-0.5 rounded-full uppercase tracking-wider',
                own.status === 'ok' ? 'bg-[#e6f4ea] text-[#137333]' : 'bg-[#fce8e6] text-[#c5221f]',
              ]"
            >
              {{ own.status }}
            </span>
          </div>

          <dl class="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2 text-sm">
            <div class="flex justify-between gap-3">
              <dt class="text-[#747775]">Last check</dt>
              <dd>{{ own.last_check_at ? formatDate(own.last_check_at) : 'Never' }}</dd>
            </div>
            <div v-if="own.status === 'down' || own.reason" class="flex justify-between gap-3 sm:col-span-2">
              <dt class="text-[#747775]">Last result</dt>
              <dd :class="own.status === 'down' ? 'text-[#c5221f]' : ''">{{ reasonLabel(own.reason) }}</dd>
            </div>
          </dl>

          <div class="flex flex-wrap items-center gap-2 mt-5">
            <button type="button" :class="secondaryBtn" :disabled="busy.test" @click="handleTest">
              {{ busy.test ? 'Testing...' : 'Test connection' }}
            </button>
            <button type="button" :class="secondaryBtn" @click="confirmDisconnect">Disconnect</button>
          </div>

          <p v-if="testResult" :class="['mt-3 text-sm', testResult.ok ? 'text-[#137333]' : 'text-[#c5221f]']">
            {{ testResult.ok ? 'Connection works.' : `Connection failed: ${reasonLabel(testResult.reason)}.` }}
          </p>
          <p v-if="statusError" class="mt-3 text-sm text-[#c5221f]">{{ statusError }}</p>
        </section>

        <!-- Upload target -->
        <section v-if="connected && systemAllowed" class="bg-white rounded-3xl border border-gray-150 p-5 shadow-xs">
          <h2 class="text-base font-medium mb-1">Upload new files to</h2>
          <p class="text-xs text-[#747775] mb-4">
            Existing files always stay where they were uploaded and can be opened either way.
          </p>
          <div class="flex flex-col gap-2">
            <label :class="['flex items-center gap-3 p-3.5 rounded-2xl border cursor-pointer', targetRadio('own')]">
              <input v-model="target" type="radio" value="own" :disabled="busy.target" class="w-4 h-4 text-[#0b57d0] focus:ring-[#0b57d0] cursor-pointer" @change="handleTargetChange" />
              <span class="text-sm font-medium">Own Telegram account</span>
            </label>
            <label :class="['flex items-center gap-3 p-3.5 rounded-2xl border cursor-pointer', targetRadio('system')]">
              <input v-model="target" type="radio" value="system" :disabled="busy.target" class="w-4 h-4 text-[#0b57d0] focus:ring-[#0b57d0] cursor-pointer" @change="handleTargetChange" />
              <span class="text-sm font-medium">System storage</span>
            </label>
          </div>
          <p v-if="targetError" class="mt-3 text-sm text-[#c5221f]">{{ targetError }}</p>
        </section>

        <!-- System quota -->
        <section v-if="systemAllowed" class="bg-white rounded-3xl border border-gray-150 p-5 shadow-xs">
          <div class="flex items-center justify-between gap-3 mb-3">
            <h2 class="text-base font-medium">System storage</h2>
            <span class="text-sm text-[#444746]">
              {{ formatBytes(quota.used) }}
              <template v-if="quota.quota != null"> of {{ formatBytes(quota.quota) }}</template>
              <template v-else> (Unlimited)</template>
            </span>
          </div>
          <div class="w-full bg-[#e1e3e1] rounded-full h-1.5 overflow-hidden">
            <div
              class="bg-[#0b57d0] h-full rounded-full transition-all duration-300"
              :style="{ width: quotaPercent + '%' }"
            ></div>
          </div>
          <p class="text-xs text-[#747775] mt-2">Usage of the shared system storage under your account.</p>
        </section>
      </template>
    </main>

    <ConfirmModal />
    <ToastContainer />
  </div>
</template>

<script setup>
import { ref, reactive, computed, nextTick, onMounted } from 'vue';
import { ArrowLeft, Cloud } from 'lucide-vue-next';
import TelegramLoginWizard from '../components/storage/TelegramLoginWizard.vue';
import ConfirmModal from '../components/feedback/ConfirmModal.vue';
import ToastContainer from '../components/feedback/ToastContainer.vue';
import { useStorageStore } from '../stores/storage';
import { useFeedbackStore } from '../stores/feedback';
import { testMyStorage, disconnectMyStorage, updateMyStorage, reasonLabel, errorText } from '../services/storage';

const storageStore = useStorageStore();
const feedback = useFeedbackStore();

const secondaryBtn = 'px-4 py-2 rounded-full text-sm font-medium text-[#0b57d0] bg-[#f0f4f9] hover:bg-[#e1e9f7] disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer';

const isLoading = ref(true);
const loadError = ref('');
const consent = ref(false);
const wizardRef = ref(null);
const wizardActive = ref(false);

const busy = reactive({ test: false, target: false });
const testResult = ref(null);
const statusError = ref('');
const targetError = ref('');
const target = ref('own');

const me = computed(() => storageStore.myStorage);
const own = computed(() => me.value?.own || {});
const connected = computed(() => !!own.value.connected);
const systemAllowed = computed(() => !!me.value?.system_allowed);
const loginPending = computed(() => !own.value.connected && !!me.value?.login_pending);
const quota = computed(() => me.value?.system_quota || {});

const quotaPercent = computed(() => {
  if (quota.value.quota == null || quota.value.quota === 0) return 100;
  return Math.min(100, Math.round(((quota.value.used || 0) / quota.value.quota) * 100));
});

const formatDate = (value) => new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });

const formatBytes = (bytes) => {
  if (!bytes) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
};

const targetRadio = (value) => (target.value === value ? 'border-[#0b57d0] bg-[#f0f4f9]' : 'border-gray-200 hover:bg-[#f8fafd]');

const applyMe = (data) => {
  storageStore.myStorage = data;
  target.value = data.upload_target || 'own';
};

const refresh = async () => {
  const data = await storageStore.fetchMyStorage();
  target.value = data.upload_target || 'own';
  return data;
};

const handleConnected = async (data) => {
  try {
    await refresh();
    if (data?.storage_ok) {
      feedback.showToast('success', data.account ? `Connected as ${data.account}` : 'Telegram account connected');
    } else {
      feedback.showToast('error', `Signed in, but the storage check failed at "${data?.storage_step || 'unknown'}": ${reasonLabel(data?.storage_reason)}`);
    }
  } catch (err) {
    loadError.value = errorText(err, 'Could not refresh the status');
  }
};

const handleTest = async () => {
  busy.test = true;
  testResult.value = null;
  statusError.value = '';
  try {
    const { data } = await testMyStorage();
    testResult.value = data;
    await refresh();
  } catch (err) {
    statusError.value = errorText(err, 'Connection test failed to run');
  } finally {
    busy.test = false;
  }
};

const confirmDisconnect = () => {
  feedback.openConfirm({
    title: 'Disconnect Telegram?',
    message: 'Files stored in this account will be unavailable until you reconnect the same Telegram account.',
    confirmText: 'Disconnect',
    isDanger: true,
    onConfirm: async () => {
      try {
        await disconnectMyStorage();
        await refresh();
        feedback.showToast('success', 'Telegram account disconnected');
      } catch (err) {
        feedback.showToast('error', errorText(err, 'Could not disconnect'));
      }
    },
  });
};

const handleTargetChange = async () => {
  busy.target = true;
  targetError.value = '';
  try {
    const { data } = await updateMyStorage({ upload_target: target.value });
    applyMe(data);
    feedback.showToast('success', 'Upload target updated');
  } catch (err) {
    targetError.value = errorText(err, 'Could not change the upload target');
    try {
      await refresh();
    } catch (_) {
      // keep the local choice; a later reload will resync
    }
  } finally {
    busy.target = false;
  }
};

onMounted(async () => {
  let data = null;
  try {
    data = await refresh();
  } catch (err) {
    loadError.value = errorText(err, 'Failed to load your storage');
  } finally {
    isLoading.value = false;
  }
  if (data && loginPending.value && data.login_seconds_left > 0) {
    consent.value = true;
    // The wizard only mounts after loading is off and consent is set — let the DOM catch up.
    await nextTick();
    wizardRef.value?.resume(data.login_seconds_left);
  }
});
</script>
