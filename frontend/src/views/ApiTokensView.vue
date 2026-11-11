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
      <Key class="w-5 h-5 text-[#0b57d0]" />
      <h1 class="text-[20px] sm:text-[22px] font-normal tracking-tight">API tokens</h1>
    </header>

    <main class="max-w-3xl mx-auto p-4 sm:p-6 flex flex-col gap-6">
      <!-- Create form -->
      <section class="bg-white rounded-3xl border border-gray-150 p-5 shadow-xs">
        <h2 class="text-base font-medium mb-4">Create a token</h2>
        <div class="flex flex-col gap-4">
          <div>
            <label class="block text-xs text-[#444746] mb-1.5" for="token-name">Name</label>
            <input
              id="token-name"
              v-model="form.name"
              type="text"
              placeholder="e.g. studio"
              class="w-full h-10 px-3.5 rounded-lg bg-[#f8fafd] border border-gray-200 focus:bg-white focus:border-[#0b57d0] focus:outline-none text-sm"
            />
          </div>

          <div>
            <span class="block text-xs text-[#444746] mb-1.5">Scopes</span>
            <div class="flex flex-wrap gap-x-6 gap-y-2">
              <label v-for="scope in SCOPES" :key="scope.value" class="flex items-center gap-2 text-sm cursor-pointer">
                <input v-model="form.scopes" type="checkbox" :value="scope.value" class="accent-[#0b57d0]" />
                <span>{{ scope.label }}</span>
              </label>
            </div>
          </div>

          <div>
            <span class="block text-xs text-[#444746] mb-1.5">Folder access</span>
            <button
              type="button"
              class="flex items-center gap-2 px-3.5 h-10 rounded-lg bg-[#f8fafd] border border-gray-200 hover:bg-[#f0f4f9] text-sm cursor-pointer"
              @click="isPickerOpen = !isPickerOpen"
            >
              <Folder class="w-4 h-4 text-[#0b57d0]" />
              <span>{{ form.folderId ? pickedFolderName : 'All folders' }}</span>
            </button>
            <div v-if="isPickerOpen" class="mt-2 border border-gray-150 rounded-xl overflow-hidden bg-[#f8fafd]">
              <div class="px-3 py-2 bg-[#eef3fb] flex flex-wrap items-center gap-1 text-xs text-[#444746] border-b border-gray-100">
                <button type="button" class="hover:text-[#0b57d0] hover:underline cursor-pointer font-medium"
                  :class="pickTrail.length === 0 ? 'text-[#0b57d0] font-semibold' : ''" @click="pickRoot">
                  My Drive
                </button>
                <template v-for="crumb in pickTrail" :key="crumb.id">
                  <ChevronRight class="w-3 h-3 text-gray-400" />
                  <button type="button" class="hover:text-[#0b57d0] hover:underline cursor-pointer"
                    @click="pickFolder(crumb.id, crumb.name)">
                    {{ crumb.name }}
                  </button>
                </template>
              </div>
              <div class="max-h-56 overflow-y-auto p-2 flex flex-col gap-1">
                <div v-if="pickerLoading" class="py-8 flex justify-center">
                  <div class="animate-spin rounded-full h-6 w-6 border-2 border-[#0b57d0] border-t-transparent"></div>
                </div>
                <div v-else-if="pickFolders.length === 0" class="py-6 text-center text-xs text-[#747775]">
                  No subfolders here
                </div>
                <button
                  v-else
                  v-for="folder in pickFolders"
                  :key="folder.id"
                  type="button"
                  class="flex items-center justify-between px-3 py-2 rounded-lg hover:bg-[#f0f4f9] text-sm cursor-pointer text-left"
                  @click="pickFolder(folder.id, folder.name)"
                >
                  <span class="flex items-center gap-2.5 truncate">
                    <Folder class="w-4 h-4 text-[#0b57d0] fill-[#c2e7ff] shrink-0" />
                    <span class="truncate">{{ folder.name }}</span>
                  </span>
                  <ChevronRight class="w-4 h-4 text-gray-400 shrink-0" />
                </button>
              </div>
              <div class="px-3 py-2 border-t border-gray-100 flex items-center justify-between">
                <span class="text-xs text-[#444746] truncate">
                  {{ form.folderId ? `Restrict to: ${pickedFolderName}` : 'Token can access all folders' }}
                </span>
                <button type="button" class="text-xs font-medium text-[#0b57d0] hover:underline cursor-pointer"
                  @click="clearPickedFolder">
                  Use all folders
                </button>
              </div>
            </div>
          </div>

          <div class="flex justify-end">
            <button
              type="button"
              :disabled="!canCreate || isCreating"
              :class="[
                'px-5 py-2.5 rounded-full text-sm font-medium flex items-center gap-2 shadow-xs transition-all',
                canCreate && !isCreating ? 'bg-[#0b57d0] hover:bg-[#0842a0] text-white cursor-pointer' : 'bg-gray-200 text-gray-400 cursor-not-allowed shadow-none',
              ]"
              @click="handleCreate"
            >
              <div v-if="isCreating" class="animate-spin rounded-full h-3.5 w-3.5 border-2 border-white border-t-transparent"></div>
              Create token
            </button>
          </div>
        </div>
      </section>

      <!-- New token plaintext (shown once) -->
      <section
        v-if="freshToken"
        class="bg-[#e6f4ea] border border-[#a8dab5] rounded-3xl p-5"
      >
        <div class="flex items-center gap-2 mb-2">
          <CheckCircle class="w-5 h-5 text-[#188038]" />
          <h2 class="text-sm font-medium text-[#188038]">Token created</h2>
        </div>
        <div class="bg-white rounded-xl px-3.5 py-2.5 font-mono text-sm break-all border border-[#a8dab5]">
          {{ freshToken }}
        </div>
        <div class="flex items-center justify-between mt-2.5">
          <p class="text-xs text-[#137333]">Copy this token now. You will not be able to see it again.</p>
          <button
            type="button"
            class="shrink-0 ml-3 px-4 py-1.5 rounded-full text-xs font-medium bg-[#188038] hover:bg-[#106b2f] text-white flex items-center gap-1.5 cursor-pointer"
            @click="copyFreshToken"
          >
            <Copy v-if="!copied" class="w-3.5 h-3.5" />
            <Check v-else class="w-3.5 h-3.5" />
            {{ copied ? 'Copied' : 'Copy' }}
          </button>
        </div>
      </section>

      <!-- Error feedback -->
      <div
        v-if="formError"
        class="bg-white border border-[#f1b7b2] rounded-2xl px-4 py-3 text-sm text-[#c5221f]"
      >
        {{ formError }}
      </div>

      <!-- Token list -->
      <section class="bg-white rounded-3xl border border-gray-150 shadow-xs overflow-hidden">
        <div v-if="isLoading" class="py-16 flex justify-center">
          <div class="animate-spin rounded-full h-7 w-7 border-2 border-[#0b57d0] border-t-transparent"></div>
        </div>
        <div v-else-if="tokens.length === 0" class="py-16 text-center">
          <Key class="w-10 h-10 text-gray-300 mx-auto mb-3" />
          <p class="text-sm text-[#747775]">No API tokens yet</p>
        </div>
        <ul v-else class="divide-y divide-gray-100">
          <li
            v-for="token in tokens"
            :key="token.id"
            class="px-4 sm:px-5 py-4 flex flex-col sm:flex-row sm:items-center gap-3"
          >
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2 flex-wrap">
                <span class="font-medium text-sm truncate">{{ token.name }}</span>
                <span
                  :class="[
                    'text-[10px] font-semibold px-2 py-0.5 rounded-full uppercase tracking-wider',
                    token.revoked_at ? 'bg-[#fce8e6] text-[#c5221f]' : 'bg-[#e6f4ea] text-[#137333]',
                  ]"
                >
                  {{ token.revoked_at ? 'Revoked' : 'Active' }}
                </span>
              </div>
              <div class="font-mono text-xs text-[#444746] mt-1">{{ token.prefix }}…</div>
              <div class="flex flex-wrap gap-1.5 mt-2">
                <span
                  v-for="scope in token.scopes"
                  :key="scope"
                  class="text-[10px] font-medium bg-[#e8f0fe] text-[#0b57d0] px-2 py-0.5 rounded-full"
                >
                  {{ scope }}
                </span>
              </div>
              <div class="text-xs text-[#747775] mt-2 flex flex-wrap gap-x-4">
                <span>Folder: {{ token.folder ? token.folder.name : 'All folders' }}</span>
                <span>Created: {{ formatDate(token.created_at) }}</span>
                <span>Last used: {{ token.last_used_at ? formatDate(token.last_used_at) : 'Never' }}</span>
              </div>
            </div>
            <button
              v-if="!token.revoked_at"
              type="button"
              class="shrink-0 self-start sm:self-auto px-4 py-1.5 rounded-full text-xs font-medium text-[#c5221f] hover:bg-red-50/80 border border-transparent hover:border-[#f1b7b2] transition-colors cursor-pointer"
              @click="confirmRevokeId = token.id"
            >
              Revoke
            </button>
          </li>
        </ul>
      </section>
    </main>

    <!-- In-page revoke confirm -->
    <Transition name="fade">
      <div v-if="confirmRevokeId" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
        <div class="bg-white rounded-3xl shadow-2xl w-full max-w-sm p-5">
          <h3 class="text-base font-medium mb-1.5">Revoke token?</h3>
          <p class="text-sm text-[#444746] mb-5">
            Applications using this token will immediately lose access. This cannot be undone.
          </p>
          <div class="flex justify-end gap-2">
            <button
              type="button"
              class="px-4 py-2 rounded-full text-sm font-medium text-[#444746] hover:bg-black/5 cursor-pointer"
              @click="confirmRevokeId = null"
            >
              Cancel
            </button>
            <button
              type="button"
              class="px-5 py-2 rounded-full text-sm font-medium bg-[#c5221f] hover:bg-[#a50e0e] text-white cursor-pointer"
              @click="handleRevoke"
            >
              Revoke
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue';
import { ArrowLeft, Key, Folder, ChevronRight, CheckCircle, Copy, Check } from 'lucide-vue-next';
import { useFeedbackStore } from '../stores/feedback';
import { listTokens, createToken, revokeToken } from '../services/tokens';
import api from '../services/api';

const SCOPES = [
  { value: 'read', label: 'read' },
  { value: 'folders:create', label: 'folders:create' },
  { value: 'files:upload', label: 'files:upload' },
];

const feedback = useFeedbackStore();

const tokens = ref([]);
const isLoading = ref(true);
const isCreating = ref(false);
const formError = ref('');
const freshToken = ref('');
const copied = ref(false);
const confirmRevokeId = ref(null);

const form = ref({ name: '', scopes: [...SCOPES.map(s => s.value)], folderId: null });
const isPickerOpen = ref(false);
const pickFolders = ref([]);
const pickTrail = ref([]);
const pickerLoading = ref(false);

const canCreate = computed(() => form.value.name.trim().length > 0 && form.value.scopes.length > 0);
const pickedFolderName = computed(() => {
  const crumb = pickTrail.value.find(c => c.id === form.value.folderId);
  return crumb ? crumb.name : 'Selected folder';
});

const formatDate = (value) => {
  if (!value) return '—';
  return new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
};

const fetchTokens = async () => {
  isLoading.value = true;
  try {
    const { data } = await listTokens();
    tokens.value = data;
  } catch (err) {
    feedback.showToast('error', 'Failed to load API tokens', 'Error');
  } finally {
    isLoading.value = false;
  }
};

const fetchPickerFolders = async (parentId = null) => {
  pickerLoading.value = true;
  try {
    const params = { trashed: false };
    if (parentId) params.parent = parentId;
    const { data } = await api.get('/drive/folders/', { params });
    pickFolders.value = data;
  } catch (err) {
    pickFolders.value = [];
  } finally {
    pickerLoading.value = false;
  }
};

const pickRoot = () => {
  form.value.folderId = null;
  pickTrail.value = [];
  fetchPickerFolders(null);
};

const pickFolder = (id, name = '') => {
  form.value.folderId = id;
  const existing = pickTrail.value.findIndex(c => c.id === id);
  if (existing !== -1) {
    pickTrail.value = pickTrail.value.slice(0, existing + 1);
  } else {
    pickTrail.value.push({ id, name });
  }
  fetchPickerFolders(id);
};

const clearPickedFolder = () => {
  form.value.folderId = null;
};

const handleCreate = async () => {
  formError.value = '';
  isCreating.value = true;
  try {
    const { data } = await createToken({
      name: form.value.name.trim(),
      scopes: form.value.scopes,
      folderId: form.value.folderId,
    });
    freshToken.value = data.token;
    form.value.name = '';
    form.value.folderId = null;
    pickTrail.value = [];
    fetchPickerFolders(null);
    await fetchTokens();
  } catch (err) {
    const detail = err.response?.data;
    formError.value =
      (typeof detail === 'string' && detail) ||
      detail?.detail ||
      detail?.scopes?.[0] ||
      detail?.folder_id?.[0] ||
      detail?.name?.[0] ||
      'Failed to create the token';
  } finally {
    isCreating.value = false;
  }
};

const copyFreshToken = async () => {
  try {
    await navigator.clipboard.writeText(freshToken.value);
    copied.value = true;
    setTimeout(() => { copied.value = false; }, 2000);
  } catch (_) {
    feedback.showToast('error', 'Copy failed — select the token text manually', 'Error');
  }
};

const handleRevoke = async () => {
  const id = confirmRevokeId.value;
  confirmRevokeId.value = null;
  try {
    await revokeToken(id);
    feedback.showToast('success', 'Token revoked', 'Done');
    await fetchTokens();
  } catch (err) {
    feedback.showToast('error', 'Failed to revoke token', 'Error');
  }
};

onMounted(() => {
  fetchTokens();
  fetchPickerFolders(null);
});
</script>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.15s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
