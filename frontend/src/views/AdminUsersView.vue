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
      <Users class="w-5 h-5 text-[#0b57d0]" />
      <h1 class="text-[20px] sm:text-[22px] font-normal tracking-tight">Users</h1>
    </header>

    <main class="max-w-5xl mx-auto p-4 sm:p-6 flex flex-col gap-6">
      <section class="bg-white rounded-3xl border border-gray-150 p-5 shadow-xs">
        <div class="flex items-center justify-between gap-3 mb-4 flex-wrap">
          <h2 class="text-base font-medium">All users</h2>
          <div class="relative">
            <Search class="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-[#444746]" />
            <input
              v-model="search"
              type="text"
              placeholder="Search by email or name"
              autocomplete="off"
              class="h-10 w-64 max-w-full pl-10 pr-3.5 rounded-lg bg-[#f8fafd] border border-gray-200 focus:bg-white focus:border-[#0b57d0] focus:outline-none text-sm"
              @keydown.enter="load()"
            />
          </div>
        </div>

        <div v-if="isLoading" class="py-16 flex justify-center">
          <div class="animate-spin rounded-full h-7 w-7 border-2 border-[#0b57d0] border-t-transparent"></div>
        </div>

        <div v-else-if="loadError" class="py-8 text-sm text-[#c5221f]">{{ loadError }}</div>

        <div v-else class="overflow-x-auto">
          <table class="w-full text-sm text-left">
            <thead class="text-xs text-[#747775] uppercase tracking-wider border-b border-gray-150">
              <tr>
                <th class="py-2.5 pr-4 font-medium">User</th>
                <th class="py-2.5 pr-4 font-medium">Storage</th>
                <th class="py-2.5 pr-4 font-medium">System used / quota</th>
                <th class="py-2.5 pr-4 font-medium">System access</th>
                <th class="py-2.5 pr-4 font-medium">Active</th>
                <th class="py-2.5 pr-4 font-medium">Quota (GB)</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="user in users" :key="user.id" class="border-b border-gray-100 last:border-0 align-middle">
                <td class="py-3 pr-4">
                  <div class="font-medium truncate max-w-[200px]">{{ user.name || '—' }}</div>
                  <div class="text-xs text-[#747775] truncate max-w-[200px]">{{ user.email }}</div>
                </td>
                <td class="py-3 pr-4">
                  <span
                    v-if="user.own.connected"
                    :class="[
                      'text-[10px] font-semibold px-2 py-0.5 rounded-full uppercase tracking-wider',
                      user.own.status === 'ok' ? 'bg-[#e6f4ea] text-[#137333]' : 'bg-[#fce8e6] text-[#c5221f]',
                    ]"
                    :title="user.own.reason ? reasonLabel(user.own.reason) : ''"
                  >
                    Own · {{ user.own.status }}
                  </span>
                  <span
                    v-else-if="user.can_use_system_storage"
                    class="text-[10px] font-semibold px-2 py-0.5 rounded-full uppercase tracking-wider bg-[#e8eaf6] text-[#4a4f8a]"
                  >
                    System
                  </span>
                  <span v-else class="text-[10px] font-semibold px-2 py-0.5 rounded-full uppercase tracking-wider bg-[#f1f3f4] text-[#747775]">None</span>
                </td>
                <td class="py-3 pr-4 whitespace-nowrap">
                  {{ formatBytes(user.storage_used) }} /
                  <template v-if="user.storage_quota != null">{{ formatBytes(user.storage_quota) }}</template>
                  <template v-else>∞</template>
                </td>
                <td class="py-3 pr-4">
                  <input
                    type="checkbox"
                    :checked="user.system_storage_allowed"
                    :disabled="savingId === user.id"
                    class="w-4 h-4 rounded border-gray-300 text-[#0b57d0] focus:ring-[#0b57d0] cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                    @change="toggleField(user, 'system_storage_allowed', $event.target.checked)"
                  />
                </td>
                <td class="py-3 pr-4">
                  <input
                    type="checkbox"
                    :checked="user.is_active"
                    :disabled="savingId === user.id || user.id === auth.user?.id"
                    :title="user.id === auth.user?.id ? 'You cannot deactivate yourself' : ''"
                    class="w-4 h-4 rounded border-gray-300 text-[#0b57d0] focus:ring-[#0b57d0] cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                    @change="toggleField(user, 'is_active', $event.target.checked)"
                  />
                </td>
                <td class="py-3 pr-4">
                  <input
                    v-model="quotaGb[user.id]"
                    type="number"
                    min="0"
                    step="1"
                    placeholder="Unlimited"
                    :disabled="savingId === user.id"
                    class="h-9 w-28 px-3 rounded-lg bg-[#f8fafd] border border-gray-200 focus:bg-white focus:border-[#0b57d0] focus:outline-none text-sm disabled:opacity-50"
                    @change="saveQuota(user)"
                  />
                </td>
              </tr>
            </tbody>
          </table>

          <p v-if="users.length === 0" class="py-8 text-sm text-center text-[#747775]">No users found.</p>
        </div>

        <div v-if="!isLoading && (hasNext || hasPrev)" class="flex items-center justify-between mt-4">
          <button type="button" :disabled="!hasPrev || isLoading || page <= 1" :class="pagerBtn" @click="goPage(page - 1)">Previous</button>
          <span class="text-xs text-[#747775]">{{ count }} users</span>
          <button type="button" :disabled="!hasNext || isLoading" :class="pagerBtn" @click="goPage(page + 1)">Next</button>
        </div>
      </section>
    </main>

    <ToastContainer />
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted, watch } from 'vue';
import { ArrowLeft, Users, Search } from 'lucide-vue-next';
import ToastContainer from '../components/feedback/ToastContainer.vue';
import { getAdminUsers, updateAdminUser, reasonLabel, errorText } from '../services/storage';
import { useAuthStore } from '../stores/auth';
import { useFeedbackStore } from '../stores/feedback';

const auth = useAuthStore();
const feedback = useFeedbackStore();

const pagerBtn = 'px-4 py-2 rounded-full text-sm font-medium text-[#0b57d0] bg-[#f0f4f9] hover:bg-[#e1e9f7] disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer';

const users = ref([]);
const count = ref(0);
const hasNext = ref(false);
const hasPrev = ref(false);
const page = ref(1);
const search = ref('');
const isLoading = ref(true);
const loadError = ref('');
const savingId = ref(null);
const quotaGb = reactive({});

let searchTimer = null;
let reqToken = 0;

const formatBytes = (bytes) => {
  if (!bytes) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
};

const indexQuotas = (list) => {
  for (const u of list) {
    quotaGb[u.id] = u.storage_quota != null ? (u.storage_quota / 1024 ** 3).toFixed(u.storage_quota % 1024 ** 3 ? 2 : 0) : '';
  }
};

const requestUsers = async () => {
  const token = ++reqToken;
  isLoading.value = true;
  loadError.value = '';
  const params = { page: page.value };
  if (search.value.trim()) params.search = search.value.trim();
  try {
    const { data } = await getAdminUsers(params);
    if (token !== reqToken) return;
    users.value = data.results ?? data;
    count.value = data.count ?? users.value.length;
    hasNext.value = !!data.next;
    hasPrev.value = !!data.previous;
    indexQuotas(users.value);
  } catch (err) {
    if (token === reqToken) loadError.value = errorText(err, 'Failed to load users');
  } finally {
    if (token === reqToken) isLoading.value = false;
  }
};

const load = () => {
  page.value = 1;
  requestUsers();
};

const goPage = (p) => {
  page.value = p;
  requestUsers();
};

const saveUser = async (user, payload) => {
  if (savingId.value === user.id) return;
  savingId.value = user.id;
  try {
    const { data } = await updateAdminUser(user.id, payload);
    Object.assign(user, data);
    if ('storage_quota' in payload) indexQuotas([data]);
    feedback.showToast('success', `Saved ${data.email}`);
  } catch (err) {
    feedback.showToast('error', errorText(err, 'Could not save'));
    load();
  } finally {
    savingId.value = null;
  }
};

const toggleField = (user, field, value) => saveUser(user, { [field]: value });

const saveQuota = (user) => {
  const raw = String(quotaGb[user.id] ?? '').trim();
  const current = user.storage_quota;
  if (raw === '') {
    if (current === null || current === undefined) return;
    saveUser(user, { storage_quota: null });
    return;
  }
  const gb = Number(raw);
  if (Number.isNaN(gb) || gb < 0) {
    quotaGb[user.id] = current != null ? (current / 1024 ** 3).toFixed(0) : '';
    feedback.showToast('error', 'Quota must be a number in GB or blank for unlimited');
    return;
  }
  const bytes = Math.round(gb * 1024 ** 3);
  if (bytes === current) return;
  saveUser(user, { storage_quota: bytes });
};

watch(search, () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => load(), 400);
});

onMounted(load);

onUnmounted(() => clearTimeout(searchTimer));
</script>
