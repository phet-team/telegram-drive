<template>
  <Transition name="fade">
    <div
      v-if="isOpen"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4 select-none"
    >
      <div
        class="bg-white rounded-[28px] shadow-[0_8px_32px_rgba(0,0,0,0.18)] max-w-lg w-full p-4 sm:p-6 border border-gray-150 animate-in fade-in zoom-in-95 duration-150 max-h-[90vh] overflow-y-auto"
        @click.stop
      >
        <div class="flex items-center justify-between mb-4 sm:mb-5">
          <h3 class="text-xl sm:text-2xl font-normal text-[#1f1f1f] truncate max-w-xs sm:max-w-md">
            Share "{{ item?.name }}"
          </h3>
          <button
            type="button"
            class="text-[#444746] hover:text-[#1f1f1f] hover:bg-black/5 p-2 rounded-full transition-colors cursor-pointer"
            title="Close"
            @click="emit('close')"
          >
            <X class="w-5 h-5" />
          </button>
        </div>

        <!-- Add People -->
        <div class="mb-5">
          <label class="block text-xs font-semibold text-[#444746] uppercase tracking-wider mb-2">
            Add people and groups
          </label>
          <div class="flex flex-col sm:flex-row gap-2">
            <input
              v-model="inviteEmail"
              type="email"
              placeholder="Enter email address"
              class="w-full sm:flex-1 px-4 py-2 border border-gray-300 rounded-xl text-sm focus:outline-none focus:border-[#0b57d0] focus:ring-2 focus:ring-[#0b57d0]/20"
              @keyup.enter="handleInvite"
            />
            <div class="flex gap-2">
              <select
                v-model="inviteRole"
                class="flex-1 sm:w-auto px-3 py-2 border border-gray-300 rounded-xl text-sm bg-white focus:outline-none focus:border-[#0b57d0] cursor-pointer"
              >
                <option value="viewer">Viewer</option>
                <option value="editor">Editor</option>
              </select>
              <button
                type="button"
                class="px-5 py-2 bg-[#0b57d0] text-white rounded-xl text-sm font-medium hover:bg-[#0842a0] transition-colors disabled:opacity-40 cursor-pointer shadow-xs"
                :disabled="!inviteEmail.trim() || isSubmitting"
                @click="handleInvite"
              >
                {{ isSubmitting ? 'Adding...' : 'Add' }}
              </button>
            </div>
          </div>
        </div>

        <!-- People with access -->
        <div class="mb-6">
          <label class="block text-xs font-semibold text-[#444746] uppercase tracking-wider mb-2">
            People with access
          </label>
          <div class="bg-gray-50/60 rounded-2xl p-3 border border-gray-150 flex flex-col divide-y divide-gray-100 max-h-44 overflow-y-auto">
            <!-- Owner row -->
            <div class="py-2 flex items-center justify-between">
              <div class="flex items-center gap-3 min-w-0">
                <img
                  v-if="ownerInfo.avatar"
                  :src="ownerInfo.avatar"
                  class="w-8 h-8 rounded-full object-cover shrink-0 border border-gray-200"
                />
                <div
                  v-else
                  class="w-8 h-8 rounded-full bg-[#0b57d0] text-white flex items-center justify-center text-xs font-semibold shrink-0 uppercase"
                >
                  {{ ownerInfo.initial }}
                </div>
                <div class="min-w-0">
                  <div class="text-xs font-medium text-[#1f1f1f] truncate">
                    {{ isCurrentUserOwner ? (auth.user?.name || 'You') : ownerInfo.name }}
                    <span v-if="isCurrentUserOwner" class="text-gray-400 font-normal text-[11px]"> (you)</span>
                  </div>
                  <div class="text-[11px] text-[#747775] truncate">{{ ownerInfo.identifier }}</div>
                </div>
              </div>
              <span class="text-xs text-[#747775] font-medium px-2.5 py-1 bg-white border border-gray-200 rounded-lg">Owner</span>
            </div>

            <!-- Collaborators rows -->
            <div
              v-for="perm in collaborators"
              :key="perm.id"
              class="py-2 flex items-center justify-between"
            >
              <div class="flex items-center gap-3 min-w-0">
                <img
                  v-if="formatUserDisplay(perm, auth.user).avatar"
                  :src="formatUserDisplay(perm, auth.user).avatar"
                  class="w-8 h-8 rounded-full object-cover shrink-0 border border-gray-200"
                />
                <div
                  v-else
                  class="w-8 h-8 rounded-full bg-emerald-600 text-white flex items-center justify-center text-xs font-semibold shrink-0 uppercase"
                >
                  {{ formatUserDisplay(perm, auth.user).initial }}
                </div>
                <div class="min-w-0">
                  <div class="text-xs font-medium text-[#1f1f1f] truncate">
                    {{ formatUserDisplay(perm, auth.user).name }}
                    <span v-if="formatUserDisplay(perm, auth.user).isMe" class="text-gray-400 font-normal text-[11px]"> (you)</span>
                  </div>
                  <div class="text-[11px] text-[#747775] truncate">
                    {{ formatUserDisplay(perm, auth.user).identifier }}
                  </div>
                </div>
              </div>

              <div class="flex items-center gap-2 shrink-0">
                <select
                  :value="perm.role"
                  class="px-2.5 py-1 border border-gray-300 rounded-lg text-xs bg-white focus:outline-none focus:border-[#0b57d0] cursor-pointer"
                  @change="handleUpdateRole(perm, $event.target.value)"
                >
                  <option value="viewer">Viewer</option>
                  <option value="editor">Editor</option>
                </select>
                <button
                  type="button"
                  class="text-gray-400 hover:text-rose-600 p-1.5 rounded-lg hover:bg-rose-50 transition-colors cursor-pointer"
                  title="Remove access"
                  @click="handleRemoveAccess(perm)"
                >
                  <Trash2 class="w-3.5 h-3.5" />
                </button>
              </div>
            </div>

            <div v-if="collaborators.length === 0 && !isLoadingCollaborators" class="py-2 text-center text-xs text-gray-400">
              Only you currently have access
            </div>
            <div v-if="isLoadingCollaborators" class="py-2 text-center text-xs text-gray-400">
              Loading access list...
            </div>
          </div>
        </div>

        <!-- General Access & Public Link -->
        <div class="border-t border-gray-100 pt-5 mb-6">
          <label class="block text-xs font-semibold text-[#444746] uppercase tracking-wider mb-3">
            General access
          </label>

          <div class="bg-[#f8fafd] p-4 rounded-2xl border border-gray-200/80 flex flex-col gap-3">
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-3">
                <div class="w-9 h-9 rounded-full bg-[#d3e3fd] text-[#0b57d0] flex items-center justify-center shrink-0">
                  <Globe class="w-5 h-5" />
                </div>
                <div>
                  <div class="text-sm font-medium text-[#1f1f1f]">Anyone with the link</div>
                  <div class="text-xs text-[#747775]">Anyone who has the link can access</div>
                </div>
              </div>

              <select
                v-model="linkRole"
                class="px-3 py-1.5 border border-gray-300 rounded-lg text-xs bg-white focus:outline-none focus:border-[#0b57d0] cursor-pointer"
              >
                <option value="viewer">Viewer</option>
                <option value="editor">Editor</option>
              </select>
            </div>

            <!-- Optional Link Password -->
            <div class="flex items-center gap-2 mt-1">
              <input
                v-model="linkPassword"
                type="password"
                placeholder="Password protection (Optional)"
                class="flex-1 px-3.5 py-2 border border-gray-300 rounded-lg text-xs focus:outline-none focus:border-[#0b57d0] bg-white"
              />
              <button
                type="button"
                class="px-4 py-2 bg-white hover:bg-gray-100 text-[#1f1f1f] border border-gray-300 rounded-lg text-xs font-medium transition-colors cursor-pointer"
                @click="handleGenerateLink"
              >
                Create link
              </button>
            </div>

            <!-- Generated link display -->
            <div v-if="generatedUrl" class="mt-2 flex items-center justify-between bg-white p-2.5 sm:p-3 rounded-xl border border-gray-200 gap-2">
              <span class="text-xs text-[#444746] truncate min-w-0 flex-1 select-all font-mono">
                {{ generatedUrl }}
              </span>
              <button
                type="button"
                class="px-3 sm:px-4 py-1.5 bg-[#c2e7ff] text-[#001d35] rounded-full font-medium text-xs hover:bg-[#b3e0fc] transition-colors shrink-0 flex items-center gap-1.5 cursor-pointer"
                @click="copyLink"
              >
                <Link2 class="w-3.5 h-3.5" />
                <span class="hidden xs:inline">Copy link</span>
                <span class="xs:hidden">Copy</span>
              </button>
            </div>
          </div>
        </div>

        <div class="flex justify-end">
          <button
            type="button"
            class="px-6 py-2.5 text-sm font-medium text-white bg-[#0b57d0] hover:bg-[#0842a0] rounded-full transition-all shadow-xs cursor-pointer"
            @click="emit('close')"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  </Transition>
</template>

<script setup>
import { ref, computed, watch } from 'vue';
import { X, Globe, Link2, Trash2 } from 'lucide-vue-next';
import api from '../../services/api';
import { useFeedbackStore } from '../../stores/feedback';
import { useAuthStore } from '../../stores/auth';
import { formatUserDisplay } from '../../utils/user';

const props = defineProps({
  isOpen: Boolean,
  item: Object,
});
const emit = defineEmits(['close']);

const feedback = useFeedbackStore();
const auth = useAuthStore();
const inviteEmail = ref('');
const inviteRole = ref('viewer');
const linkRole = ref('viewer');
const linkPassword = ref('');
const generatedUrl = ref('');
const isSubmitting = ref(false);
const collaborators = ref([]);
const isLoadingCollaborators = ref(false);

const isCurrentUserOwner = computed(() => {
  if (!props.item?.owner_email) return true;
  return props.item.owner_email.toLowerCase() === auth.user?.email?.toLowerCase();
});

const ownerInfo = computed(() => {
  if (isCurrentUserOwner.value) {
    return formatUserDisplay(auth.user, auth.user);
  }
  return formatUserDisplay(props.item, auth.user);
});

const fetchCollaborators = async () => {
  if (!props.item?.id) return;
  isLoadingCollaborators.value = true;
  try {
    const params = props.item.type === 'folder'
      ? { folder: props.item.id }
      : { file: props.item.id };
    const res = await api.get('/drive/permissions/', { params });
    collaborators.value = res.data;
  } catch (err) {
    collaborators.value = [];
  } finally {
    isLoadingCollaborators.value = false;
  }
};

const handleUpdateRole = async (perm, newRole) => {
  try {
    await api.patch(`/drive/permissions/${perm.id}/`, { role: newRole });
    perm.role = newRole;
    feedback.showToast('success', `Role updated to ${newRole}`);
  } catch (err) {
    feedback.showToast('error', 'Failed to update role');
  }
};

const handleRemoveAccess = async (perm) => {
  try {
    await api.delete(`/drive/permissions/${perm.id}/`);
    collaborators.value = collaborators.value.filter(p => p.id !== perm.id);
    feedback.showToast('success', `Removed access for ${perm.grantee_email}`);
  } catch (err) {
    feedback.showToast('error', 'Failed to remove access');
  }
};

watch([() => props.isOpen, () => props.item?.id], ([isOpen]) => {
  if (isOpen) {
    inviteEmail.value = '';
    inviteRole.value = 'viewer';
    linkRole.value = 'viewer';
    linkPassword.value = '';
    generatedUrl.value = '';
    fetchCollaborators();
  }
});

const handleInvite = async () => {
  if (!inviteEmail.value.trim() || !props.item) return;
  isSubmitting.value = true;
  try {
    const payload = {
      user_email: inviteEmail.value.trim(),
      role: inviteRole.value,
      folder: props.item.type === 'folder' ? props.item.id : null,
      file: props.item.type === 'file' ? props.item.id : null,
    };
    await api.post('/drive/permissions/', payload);
    feedback.showToast('success', `Access granted to ${inviteEmail.value}`);
    inviteEmail.value = '';
    await fetchCollaborators();
  } catch (err) {
    feedback.showToast('error', err.response?.data?.user_email?.[0] || 'Failed to grant permission');
  } finally {
    isSubmitting.value = false;
  }
};

const handleGenerateLink = async () => {
  if (!props.item) return;
  try {
    const payload = {
      folder: props.item.type === 'folder' ? props.item.id : null,
      file: props.item.type === 'file' ? props.item.id : null,
      role: linkRole.value,
      password: linkPassword.value,
    };
    const { data } = await api.post('/drive/shares/', payload);
    generatedUrl.value = `${window.location.origin}/share/${data.token}`;
    feedback.showToast('success', 'Public share link created');
  } catch (err) {
    feedback.showToast('error', 'Failed to generate link');
  }
};

const copyLink = () => {
  if (!generatedUrl.value) return;
  navigator.clipboard.writeText(generatedUrl.value);
  feedback.showToast('info', 'Link copied to clipboard');
};
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
