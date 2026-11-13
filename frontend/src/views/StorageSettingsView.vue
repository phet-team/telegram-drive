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
      <HardDrive class="w-5 h-5 text-[#0b57d0]" />
      <h1 class="text-[20px] sm:text-[22px] font-normal tracking-tight">Storage</h1>
    </header>

    <main class="max-w-3xl mx-auto p-4 sm:p-6 flex flex-col gap-6">
      <div v-if="isLoading" class="py-16 flex justify-center">
        <div class="animate-spin rounded-full h-7 w-7 border-2 border-[#0b57d0] border-t-transparent"></div>
      </div>

      <div v-else-if="loadError" class="bg-white border border-[#f1b7b2] rounded-2xl px-4 py-3 text-sm text-[#c5221f]">
        {{ loadError }}
      </div>

      <template v-else-if="settings">
        <!-- Status -->
        <section class="bg-white rounded-3xl border border-gray-150 p-5 shadow-xs">
          <div class="flex items-center justify-between gap-3 mb-4">
            <h2 class="text-base font-medium">Status</h2>
            <span
              :class="[
                'text-[10px] font-semibold px-2 py-0.5 rounded-full uppercase tracking-wider',
                settings.status.alert_state === 'down' ? 'bg-[#fce8e6] text-[#c5221f]' : 'bg-[#e6f4ea] text-[#137333]',
              ]"
            >
              {{ settings.status.alert_state === 'down' ? 'Down' : 'OK' }}
            </span>
          </div>

          <dl class="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2 text-sm">
            <div class="flex justify-between gap-3">
              <dt class="text-[#747775]">Last check</dt>
              <dd>{{ settings.status.last_check_at ? formatDate(settings.status.last_check_at) : 'Never' }}</dd>
            </div>
            <div class="flex justify-between gap-3">
              <dt class="text-[#747775]">Last result</dt>
              <dd :class="settings.status.last_check_ok === false ? 'text-[#c5221f]' : ''">
                <template v-if="settings.status.last_check_ok === null">-</template>
                <template v-else-if="settings.status.last_check_ok">Working</template>
                <template v-else>{{ reasonLabel(settings.status.last_check_reason) }}</template>
              </dd>
            </div>
            <div class="flex justify-between gap-3">
              <dt class="text-[#747775]">Session source</dt>
              <dd>{{ settings.effective_source === 'db' ? 'Database (set here)' : 'Server environment' }}</dd>
            </div>
            <div v-if="settings.credentials_unreadable" class="sm:col-span-2 text-[#c5221f]">
              The stored session cannot be decrypted. Reconnect Telegram below.
            </div>
          </dl>

          <div class="flex flex-wrap items-center gap-2 mt-5">
            <button type="button" :class="secondaryBtn" :disabled="busy.test" @click="handleTest">
              {{ busy.test ? 'Testing...' : 'Test connection' }}
            </button>
            <button type="button" :class="secondaryBtn" :disabled="busy.selftest" @click="handleSelftest(1)">Self-test 1 MB</button>
            <button type="button" :class="secondaryBtn" :disabled="busy.selftest" @click="handleSelftest(8)">Self-test 8 MB</button>
            <span v-if="busy.selftest" class="text-xs text-[#747775]">Running self-test, this can take a while...</span>
          </div>

          <p v-if="testResult" :class="['mt-3 text-sm', testResult.ok ? 'text-[#137333]' : 'text-[#c5221f]']">
            {{ testResult.ok ? 'Connection works.' : `Connection failed: ${reasonLabel(testResult.reason)}.` }}
          </p>
          <p v-if="selftestResult" :class="['mt-2 text-sm', selftestResult.ok ? 'text-[#137333]' : 'text-[#c5221f]']">
            <template v-if="selftestResult.ok">
              Self-test {{ selftestResult.size_mb }} MB passed: upload {{ selftestResult.up_s }}s,
              download {{ selftestResult.down_s }}s, delete {{ selftestResult.delete_s }}s.
            </template>
            <template v-else>
              Self-test failed at step "{{ selftestResult.failed_step }}": {{ reasonLabel(selftestResult.reason) }}.
            </template>
          </p>
          <p v-if="statusError" class="mt-3 text-sm text-[#c5221f]">{{ statusError }}</p>
        </section>

        <!-- Reconnect Telegram -->
        <section class="bg-white rounded-3xl border border-gray-150 p-5 shadow-xs">
          <h2 class="text-base font-medium mb-1">Reconnect Telegram</h2>
          <p class="text-xs text-[#747775] mb-4">
            Signs the server in to Telegram again. The new session is stored encrypted in the database.
          </p>

          <TelegramLoginWizard ref="wizardRef" :api-base-path="'/admin/storage'" @connected="handleConnected" />
        </section>

        <!-- Alerts -->
        <section class="bg-white rounded-3xl border border-gray-150 p-5 shadow-xs">
          <h2 class="text-base font-medium mb-1">Alerts</h2>
          <p class="text-xs text-[#747775] mb-4">
            Sent when storage goes down (and repeated at the interval below) and once when it recovers.
          </p>
          <form class="flex flex-col gap-4" @submit.prevent="handleSaveAlerts">
            <div>
              <label class="block text-xs text-[#444746] mb-1.5" for="alert-format">Format</label>
              <select id="alert-format" v-model="alerts.format" :class="inputCls">
                <option value="ntfy">ntfy</option>
                <option value="discord">Discord webhook</option>
                <option value="slack">Slack webhook</option>
                <option value="generic">Generic JSON</option>
              </select>
            </div>
            <div>
              <label class="block text-xs text-[#444746] mb-1.5" for="alert-url">Webhook URL (https)</label>
              <input
                id="alert-url"
                v-model="alerts.webhookUrl"
                type="password"
                autocomplete="off"
                :placeholder="settings.alert_webhook_set ? `Configured (${settings.alert_webhook_host}). Type to replace.` : 'https://ntfy.sh/your-topic'"
                :class="inputCls"
              />
              <button
                v-if="settings.alert_webhook_set"
                type="button"
                class="mt-1.5 text-xs font-medium text-[#c5221f] hover:underline cursor-pointer"
                @click="handleClearWebhook"
              >
                Remove webhook
              </button>
            </div>
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label class="block text-xs text-[#444746] mb-1.5" for="alert-tg">Telegram user id (optional DM)</label>
                <input id="alert-tg" v-model="alerts.telegramChatId" type="text" inputmode="numeric" autocomplete="off" placeholder="123456789" :class="inputCls" />
              </div>
              <div>
                <label class="block text-xs text-[#444746] mb-1.5" for="alert-interval">Repeat every (minutes, 5-1440)</label>
                <input id="alert-interval" v-model.number="alerts.interval" type="number" min="5" max="1440" :class="inputCls" />
              </div>
            </div>
            <div class="flex flex-wrap justify-end gap-2">
              <button type="button" :class="secondaryBtn" :disabled="busy.testAlert" @click="handleTestAlert">
                {{ busy.testAlert ? 'Sending...' : 'Send test alert' }}
              </button>
              <button type="submit" :disabled="busy.saveAlerts" :class="primaryBtn(!busy.saveAlerts)">
                {{ busy.saveAlerts ? 'Saving...' : 'Save alerts' }}
              </button>
            </div>
          </form>
          <ul v-if="alertResults" class="mt-3 text-sm flex flex-col gap-1">
            <li v-for="(result, channel) in alertResults" :key="channel" :class="result === 'ok' ? 'text-[#137333]' : 'text-[#c5221f]'">
              {{ channel }}: {{ result === 'ok' ? 'delivered' : result }}
            </li>
          </ul>
          <p v-if="alertsError" class="mt-3 text-sm text-[#c5221f]">{{ alertsError }}</p>
          <p v-if="alertsSaved" class="mt-3 text-sm text-[#137333]">Saved.</p>
        </section>

        <!-- Advanced -->
        <section class="bg-white rounded-3xl border border-gray-150 shadow-xs">
          <button
            type="button"
            class="w-full flex items-center justify-between px-5 py-4 text-left cursor-pointer"
            @click="advancedOpen = !advancedOpen"
          >
            <span class="text-base font-medium">Advanced</span>
            <ChevronDown :class="['w-4 h-4 text-gray-400 transition-transform', advancedOpen ? 'rotate-180' : '']" />
          </button>
          <form v-if="advancedOpen" class="px-5 pb-5 flex flex-col gap-4" @submit.prevent="handleSaveAdvanced">
            <div>
              <label class="block text-xs text-[#444746] mb-1.5" for="adv-chat">Storage chat id</label>
              <input id="adv-chat" v-model="advanced.chatId" type="text" autocomplete="off" placeholder="blank = Saved Messages" :class="inputCls" />
              <p class="text-xs text-[#747775] mt-1">A numeric chat id (e.g. -100123...) or @username. Leave blank to keep using Saved Messages.</p>
            </div>
            <div>
              <label class="block text-xs text-[#444746] mb-1.5" for="adv-session">Paste a session string</label>
              <input
                id="adv-session"
                v-model="advanced.sessionString"
                type="password"
                autocomplete="off"
                :placeholder="settings.has_session ? 'A session is stored. Type to replace it.' : 'Telethon StringSession'"
                :class="inputCls"
              />
              <p class="text-xs text-[#747775] mt-1">Write-only. Normally you do not need this: use Reconnect Telegram.</p>
            </div>
            <div class="flex justify-end">
              <button type="submit" :disabled="busy.saveAdvanced" :class="primaryBtn(!busy.saveAdvanced)">
                {{ busy.saveAdvanced ? 'Saving...' : 'Save' }}
              </button>
            </div>
            <p v-if="advancedError" class="text-sm text-[#c5221f]">{{ advancedError }}</p>
            <p v-if="advancedSaved" class="text-sm text-[#137333]">Saved.</p>
          </form>
        </section>
      </template>
    </main>
  </div>
</template>

<script setup>
import { ref, reactive, nextTick, onMounted } from 'vue';
import { ArrowLeft, HardDrive, ChevronDown } from 'lucide-vue-next';
import {
  getStorageSettings, updateStorageSettings, testStorage, sendTestAlert, runSelftest,
  reasonLabel, errorText,
} from '../services/storage';
import TelegramLoginWizard from '../components/storage/TelegramLoginWizard.vue';

const inputCls = 'w-full h-10 px-3.5 rounded-lg bg-[#f8fafd] border border-gray-200 focus:bg-white focus:border-[#0b57d0] focus:outline-none text-sm';
const secondaryBtn = 'px-4 py-2 rounded-full text-sm font-medium text-[#0b57d0] bg-[#f0f4f9] hover:bg-[#e1e9f7] disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer';
const primaryBtn = (enabled) => [
  'px-5 py-2.5 rounded-full text-sm font-medium shadow-xs transition-all',
  enabled ? 'bg-[#0b57d0] hover:bg-[#0842a0] text-white cursor-pointer' : 'bg-gray-200 text-gray-400 cursor-not-allowed shadow-none',
];

const settings = ref(null);
const isLoading = ref(true);
const loadError = ref('');

const busy = reactive({ test: false, selftest: false, testAlert: false, saveAlerts: false, saveAdvanced: false });
const testResult = ref(null);
const selftestResult = ref(null);
const statusError = ref('');

const alerts = reactive({ format: 'ntfy', webhookUrl: '', telegramChatId: '', interval: 30 });
const alertResults = ref(null);
const alertsError = ref('');
const alertsSaved = ref(false);

const advancedOpen = ref(false);
const advanced = reactive({ chatId: '', sessionString: '' });
const advancedError = ref('');
const advancedSaved = ref(false);

const wizardRef = ref(null);

const formatDate = (value) => new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });

const applySettings = (data) => {
  settings.value = data;
  alerts.format = data.alert_format;
  alerts.telegramChatId = data.alert_telegram_chat_id;
  alerts.interval = data.alert_min_interval_minutes;
  advanced.chatId = data.chat_id;
};

const refresh = async () => {
  const { data } = await getStorageSettings();
  applySettings(data);
  return data;
};

// -- wizard / status actions -------------------------------------------------------------------
const handleConnected = async () => {
  try {
    await refresh();
  } catch (err) {
    statusError.value = errorText(err, 'Could not refresh the status');
  }
};

const handleTest = async () => {
  busy.test = true;
  statusError.value = '';
  try {
    const { data } = await testStorage();
    testResult.value = data;
    await refresh();
  } catch (err) {
    statusError.value = errorText(err, 'Connection test failed to run');
  } finally {
    busy.test = false;
  }
};

const handleSelftest = async (sizeMb) => {
  busy.selftest = true;
  selftestResult.value = null;
  statusError.value = '';
  try {
    const { data } = await runSelftest(sizeMb);
    selftestResult.value = data;
    await refresh();
  } catch (err) {
    statusError.value = errorText(err, 'Self-test failed to run');
  } finally {
    busy.selftest = false;
  }
};

// -- alerts / advanced -----------------------------------------------------------------------
const handleSaveAlerts = async () => {
  busy.saveAlerts = true;
  alertsError.value = '';
  alertsSaved.value = false;
  const payload = {
    alert_format: alerts.format,
    alert_telegram_chat_id: alerts.telegramChatId.trim(),
    alert_min_interval_minutes: alerts.interval,
  };
  if (alerts.webhookUrl.trim()) payload.alert_webhook_url = alerts.webhookUrl.trim();
  try {
    const { data } = await updateStorageSettings(payload);
    applySettings(data);
    alerts.webhookUrl = '';
    alertsSaved.value = true;
  } catch (err) {
    alertsError.value = errorText(err, 'Could not save alert settings');
  } finally {
    busy.saveAlerts = false;
  }
};

const handleClearWebhook = async () => {
  alertsError.value = '';
  try {
    const { data } = await updateStorageSettings({ alert_webhook_url: '' });
    applySettings(data);
  } catch (err) {
    alertsError.value = errorText(err, 'Could not remove the webhook');
  }
};

const handleTestAlert = async () => {
  busy.testAlert = true;
  alertsError.value = '';
  alertResults.value = null;
  try {
    const { data } = await sendTestAlert();
    alertResults.value = data.results;
  } catch (err) {
    alertsError.value = errorText(err, 'Could not send the test alert');
  } finally {
    busy.testAlert = false;
  }
};

const handleSaveAdvanced = async () => {
  busy.saveAdvanced = true;
  advancedError.value = '';
  advancedSaved.value = false;
  const payload = { chat_id: advanced.chatId.trim() };
  if (advanced.sessionString.trim()) payload.session_string = advanced.sessionString.trim();
  try {
    const { data } = await updateStorageSettings(payload);
    applySettings(data);
    advanced.sessionString = '';
    advancedSaved.value = true;
  } catch (err) {
    advancedError.value = errorText(err, 'Could not save');
  } finally {
    busy.saveAdvanced = false;
  }
};

onMounted(async () => {
  let data = null;
  try {
    data = await refresh();
  } catch (err) {
    loadError.value = errorText(err, 'Failed to load storage settings');
  } finally {
    isLoading.value = false;
  }
  if (data && data.login_pending) {
    // The wizard only mounts once loading is off — let the DOM catch up.
    await nextTick();
    wizardRef.value?.resume(data.login_seconds_left);
  }
});
</script>
