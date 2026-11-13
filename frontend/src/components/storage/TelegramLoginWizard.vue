<template>
  <div>
    <!-- Step 1: phone -->
    <form v-if="wizard.step === 'phone'" class="flex flex-col gap-3" @submit.prevent="handleLoginStart">
      <label class="block text-xs text-[#444746]" for="wizard-phone">Phone number (international format)</label>
      <input
        id="wizard-phone"
        v-model="wizard.phone"
        type="tel"
        autocomplete="off"
        placeholder="+66812345678"
        :class="inputCls"
      />
      <div class="flex justify-end">
        <button type="submit" :disabled="!wizard.phone.trim() || wizard.busy" :class="primaryBtn(!!wizard.phone.trim() && !wizard.busy)">
          {{ wizard.busy ? 'Sending...' : 'Send code' }}
        </button>
      </div>
    </form>

    <!-- Step 2: code -->
    <form v-else-if="wizard.step === 'code'" class="flex flex-col gap-3" @submit.prevent="handleLoginVerify">
      <label class="block text-xs text-[#444746]" for="wizard-code">
        Login code sent to Telegram on your phone
        <span class="text-[#747775]">(expires in {{ countdownText }})</span>
      </label>
      <input
        id="wizard-code"
        v-model="wizard.code"
        type="password"
        inputmode="numeric"
        autocomplete="off"
        placeholder="12345"
        :class="inputCls"
      />
      <div class="flex justify-between gap-2">
        <button type="button" class="px-4 py-2 rounded-full text-sm font-medium text-[#444746] hover:bg-black/5 cursor-pointer" @click="handleLoginCancel">
          Cancel
        </button>
        <button type="submit" :disabled="!wizard.code.trim() || wizard.busy" :class="primaryBtn(!!wizard.code.trim() && !wizard.busy)">
          {{ wizard.busy ? 'Checking...' : 'Verify code' }}
        </button>
      </div>
    </form>

    <!-- Step 3: 2-step password -->
    <form v-else-if="wizard.step === 'password'" class="flex flex-col gap-3" @submit.prevent="handleLoginPassword">
      <label class="block text-xs text-[#444746]" for="wizard-password">
        This account has 2-step verification. Enter its password
        <span class="text-[#747775]">(expires in {{ countdownText }})</span>
      </label>
      <input
        id="wizard-password"
        v-model="wizard.password"
        type="password"
        autocomplete="off"
        :class="inputCls"
      />
      <div class="flex justify-between gap-2">
        <button type="button" class="px-4 py-2 rounded-full text-sm font-medium text-[#444746] hover:bg-black/5 cursor-pointer" @click="handleLoginCancel">
          Cancel
        </button>
        <button type="submit" :disabled="!wizard.password || wizard.busy" :class="primaryBtn(!!wizard.password && !wizard.busy)">
          {{ wizard.busy ? 'Checking...' : 'Sign in' }}
        </button>
      </div>
    </form>

    <!-- Done -->
    <div v-else class="flex flex-col gap-3">
      <div class="flex items-center gap-2 text-[#137333]">
        <CheckCircle class="w-5 h-5" />
        <span class="text-sm font-medium">Connected as {{ wizard.account || 'your Telegram account' }}.</span>
      </div>
      <p v-if="wizard.storageOk" class="text-sm text-[#137333]">Storage check passed (a test message was sent and removed).</p>
      <p v-else class="text-sm text-[#c5221f]">
        Signed in, but the storage check failed at "{{ wizard.storageStep }}": {{ reasonLabel(wizard.storageReason) }}.
        <template v-if="isAdminBase">Check the chat id under Advanced.</template>
      </p>
      <div class="flex justify-end">
        <button type="button" :class="secondaryBtn" @click="resetWizard">Done</button>
      </div>
    </div>

    <p v-if="wizard.error" class="mt-3 text-sm text-[#c5221f]">{{ wizard.error }}</p>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onUnmounted } from 'vue';
import { CheckCircle } from 'lucide-vue-next';
import api from '../../services/api';
import { reasonLabel, errorText } from '../../services/storage';

const props = defineProps({
  apiBasePath: { type: String, default: '/admin/storage' },
});

const emit = defineEmits(['connected', 'progress']);

const inputCls = 'w-full h-10 px-3.5 rounded-lg bg-[#f8fafd] border border-gray-200 focus:bg-white focus:border-[#0b57d0] focus:outline-none text-sm';
const secondaryBtn = 'px-4 py-2 rounded-full text-sm font-medium text-[#0b57d0] bg-[#f0f4f9] hover:bg-[#e1e9f7] disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer';
const primaryBtn = (enabled) => [
  'px-5 py-2.5 rounded-full text-sm font-medium shadow-xs transition-all',
  enabled ? 'bg-[#0b57d0] hover:bg-[#0842a0] text-white cursor-pointer' : 'bg-gray-200 text-gray-400 cursor-not-allowed shadow-none',
];

const wizard = reactive({
  step: 'phone', phone: '', code: '', password: '', busy: false, error: '',
  account: '', storageOk: true, storageStep: '', storageReason: '',
});
const secondsLeft = ref(0);
let expiresAt = 0;
let countdownTimer = null;

const isAdminBase = computed(() => props.apiBasePath === '/admin/storage');

// Tell the host view when a login flow is in progress (code/password step),
// so it can lock consent changes until the user finishes or cancels.
watch(
  () => wizard.step,
  (step) => emit('progress', step === 'code' || step === 'password'),
);

const countdownText = computed(() => {
  const m = Math.floor(secondsLeft.value / 60);
  const s = String(secondsLeft.value % 60).padStart(2, '0');
  return `${m}:${s}`;
});

const stopCountdown = () => {
  if (countdownTimer) clearInterval(countdownTimer);
  countdownTimer = null;
};

const startCountdown = (seconds) => {
  stopCountdown();
  expiresAt = Date.now() + seconds * 1000;
  secondsLeft.value = seconds;
  countdownTimer = setInterval(() => {
    secondsLeft.value = Math.max(0, Math.round((expiresAt - Date.now()) / 1000));
    if (secondsLeft.value === 0) {
      stopCountdown();
      wizard.step = 'phone';
      wizard.code = '';
      wizard.password = '';
      wizard.error = 'The login code expired. Send a new code.';
    }
  }, 1000);
};

const resetWizard = () => {
  stopCountdown();
  Object.assign(wizard, { step: 'phone', phone: '', code: '', password: '', busy: false, error: '' });
};

// Resume an in-progress flow (e.g. the user navigated back while a code was pending).
const resume = (seconds) => {
  wizard.step = 'code';
  wizard.error = '';
  startCountdown(seconds);
};

const handleLoginStart = async () => {
  wizard.busy = true;
  wizard.error = '';
  try {
    const { data } = await api.post(`${props.apiBasePath}/login/start/`, { phone: wizard.phone.trim() });
    wizard.step = 'code';
    startCountdown(data.expires_in);
  } catch (err) {
    wizard.error = errorText(err, 'Could not send the code');
  } finally {
    wizard.busy = false;
  }
};

const finishLogin = (data) => {
  stopCountdown();
  Object.assign(wizard, {
    step: 'done', code: '', password: '', account: data.account,
    storageOk: data.storage_ok, storageStep: data.storage_step || '', storageReason: data.storage_reason || '',
  });
  emit('connected', data);
};

const handleLoginVerify = async () => {
  wizard.busy = true;
  wizard.error = '';
  try {
    const { data } = await api.post(`${props.apiBasePath}/login/verify/`, { code: wizard.code.trim() });
    if (data.needs_password) {
      wizard.step = 'password';
      wizard.code = '';
    } else {
      finishLogin(data);
    }
  } catch (err) {
    wizard.error = errorText(err, 'Could not verify the code');
  } finally {
    wizard.busy = false;
  }
};

const handleLoginPassword = async () => {
  wizard.busy = true;
  wizard.error = '';
  try {
    const { data } = await api.post(`${props.apiBasePath}/login/password/`, { password: wizard.password });
    finishLogin(data);
  } catch (err) {
    wizard.error = errorText(err, 'Could not sign in');
  } finally {
    wizard.busy = false;
  }
};

const handleLoginCancel = async () => {
  try {
    await api.post(`${props.apiBasePath}/login/cancel/`);
  } catch (err) {
    wizard.error = errorText(err, 'Could not cancel the login');
    return;
  }
  resetWizard();
};

defineExpose({ resume, resetWizard });

onUnmounted(stopCountdown);
</script>
