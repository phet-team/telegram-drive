<template>
  <!-- Mobile Backdrop Overlay -->
  <Transition name="fade">
    <div
      v-if="isOpen"
      class="fixed inset-0 bg-black/40 backdrop-blur-xs z-40 lg:hidden"
      @click="emit('close')"
    ></div>
  </Transition>

  <aside
    :class="[
      'fixed inset-y-0 left-0 z-50 w-72 bg-drive-bg flex flex-col justify-between p-4 shrink-0 select-none transition-transform duration-300 shadow-2xl lg:shadow-none lg:static lg:w-64 lg:translate-x-0 overflow-y-auto overscroll-contain',
      isOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'
    ]"
  >
    <div class="flex flex-col gap-4">
      <!-- Mobile Drawer Header -->
      <div class="flex items-center justify-between pb-3 lg:hidden border-b border-gray-200/60">
        <div class="flex items-center gap-2.5">
          <GoogleDriveLogo :size="32" />
          <span class="text-lg font-normal text-[#444746]">Google Drive</span>
        </div>
        <button
          type="button"
          class="p-2 text-gray-500 hover:text-gray-800 rounded-full hover:bg-black/5 cursor-pointer"
          title="Close menu"
          @click="emit('close')"
        >
          <X class="w-5 h-5" />
        </button>
      </div>

      <!-- Google Drive + New Button -->
      <div class="relative">
        <button
          type="button"
          :disabled="!canCreateNew"
          :class="[
            'flex items-center gap-3.5 px-5 py-3 rounded-2xl transition-all font-medium text-sm',
            canCreateNew
              ? 'bg-white hover:bg-[#f8fafd] shadow-[0_1px_2px_0_rgba(60,64,67,0.3),0_1px_3px_1px_rgba(60,64,67,0.15)] hover:shadow-[0_1px_3px_0_rgba(60,64,67,0.3),0_4px_8px_3px_rgba(60,64,67,0.15)] text-[#1f1f1f] cursor-pointer'
              : 'bg-gray-100 text-[#747775] opacity-60 cursor-not-allowed shadow-none'
          ]"
          @click="canCreateNew && (isNewMenuOpen = !isNewMenuOpen)"
        >
          <!-- 4-Color Google Plus Icon -->
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M19 13H13V19H11V13H5V11H11V5H13V11H19V13Z" fill="#EA4335" />
            <path d="M11 5V11H5V13H11V19H13V13H19V11H13V5H11Z" fill="url(#gplus_grad)" />
            <defs>
              <linearGradient id="gplus_grad" x1="5" y1="5" x2="19" y2="19" gradientUnits="userSpaceOnUse">
                <stop stop-color="#4285F4"/>
                <stop offset="0.33" stop-color="#34A853"/>
                <stop offset="0.66" stop-color="#FBBC04"/>
                <stop offset="1" stop-color="#EA4335"/>
              </linearGradient>
            </defs>
          </svg>
          <span class="text-[14px] font-medium tracking-wide">New</span>
        </button>

        <!-- Google Drive New Menu Dropdown -->
        <div
          v-if="isNewMenuOpen"
          class="absolute left-0 mt-2 w-60 bg-white rounded-2xl shadow-[0_4px_20px_rgba(0,0,0,0.15)] border border-gray-150 py-2 z-40 text-sm select-none animate-in fade-in zoom-in-95 duration-100"
        >
          <button
            type="button"
            class="w-full text-left px-4 py-2.5 hover:bg-[#f0f4f9] flex items-center gap-3 transition-colors text-[#1f1f1f] cursor-pointer"
            @click="triggerCreateFolder"
          >
            <FolderPlus class="w-5 h-5 text-[#444746]" />
            <span class="text-[13.5px]">New folder</span>
          </button>
          <div class="h-px bg-gray-150 my-1"></div>
          <button
            type="button"
            class="w-full text-left px-4 py-2.5 hover:bg-[#f0f4f9] flex items-center gap-3 transition-colors text-[#1f1f1f] cursor-pointer"
            @click="triggerFileUpload"
          >
            <Upload class="w-5 h-5 text-[#444746]" />
            <span class="text-[13.5px]">File upload</span>
          </button>
        </div>
      </div>

      <!-- Hidden file input for file upload -->
      <input
        type="file"
        multiple
        ref="fileInputRef"
        class="hidden"
        @change="handleFileSelected"
      />

      <!-- Navigation Links (Google Drive Pills) -->
      <nav class="flex flex-col gap-1 mt-1">
        <button
          type="button"
          :class="[
            'w-full flex items-center gap-4 px-4 py-2 rounded-full text-[13.5px] transition-colors text-left cursor-pointer',
            drive.currentSection === 'drive'
              ? 'bg-[#c2e7ff] text-[#001d35] font-semibold'
              : 'text-[#444746] font-medium hover:bg-[#eaebef]'
          ]"
          @click="selectSection('drive')"
        >
          <HardDrive class="w-5 h-5 shrink-0" />
          <span>My Drive</span>
        </button>

        <button
          type="button"
          :class="[
            'w-full flex items-center gap-4 px-4 py-2 rounded-full text-[13.5px] transition-colors text-left cursor-pointer',
            drive.currentSection === 'shared'
              ? 'bg-[#c2e7ff] text-[#001d35] font-semibold'
              : 'text-[#444746] font-medium hover:bg-[#eaebef]'
          ]"
          @click="selectSection('shared')"
        >
          <Users class="w-5 h-5 shrink-0" />
          <span>Shared with me</span>
        </button>

        <button
          type="button"
          :class="[
            'w-full flex items-center gap-4 px-4 py-2 rounded-full text-[13.5px] transition-colors text-left cursor-pointer',
            drive.currentSection === 'starred'
              ? 'bg-[#c2e7ff] text-[#001d35] font-semibold'
              : 'text-[#444746] font-medium hover:bg-[#eaebef]'
          ]"
          @click="selectSection('starred')"
        >
          <Star class="w-5 h-5 shrink-0" />
          <span>Starred</span>
        </button>

        <button
          type="button"
          :class="[
            'w-full flex items-center gap-4 px-4 py-2 rounded-full text-[13.5px] transition-colors text-left cursor-pointer',
            drive.currentSection === 'trash'
              ? 'bg-[#c2e7ff] text-[#001d35] font-semibold'
              : 'text-[#444746] font-medium hover:bg-[#eaebef]'
          ]"
          @click="selectSection('trash')"
        >
          <Trash2 class="w-5 h-5 shrink-0" />
          <span>Trash</span>
        </button>
      </nav>
    </div>

    <!-- Storage Info Widget -->
    <div class="px-3 py-3 rounded-2xl flex flex-col gap-2 border border-transparent">
      <div class="flex items-center justify-between text-xs font-medium text-[#444746]">
        <div class="flex items-center gap-2">
          <Cloud class="w-4 h-4 text-[#444746]" />
          <span>Storage</span>
        </div>
        <span class="text-[10px] font-bold text-[#0b57d0] bg-[#d3e3fd]/60 px-2 py-0.5 rounded-full uppercase">
          Unlimited
        </span>
      </div>

      <div class="w-full bg-[#e1e3e1] rounded-full h-1 overflow-hidden">
        <div
          class="bg-[#0b57d0] h-full rounded-full transition-all duration-500"
          :style="{ width: auth.user?.storage_quota ? `${quotaPercent}%` : '100%' }"
        ></div>
      </div>

      <div class="text-[11.5px] text-[#444746]">
        <template v-if="auth.user?.storage_quota">
          {{ formatBytes(auth.user?.storage_used) }} of {{ formatBytes(auth.user?.storage_quota) }} used
        </template>
        <template v-else>
          {{ formatBytes(auth.user?.storage_used) }} used • Free Unlimited
        </template>
      </div>

      <div class="mt-1 flex items-center gap-1.5 text-[11px] text-[#0b57d0] font-medium">
        <span>⚡ Telegram MTProto Uncapped</span>
      </div>
    </div>
  </aside>
</template>

<script setup>
import { ref, computed } from 'vue';
import { FolderPlus, Upload, HardDrive, Users, Star, Trash2, Cloud, X } from 'lucide-vue-next';
import GoogleDriveLogo from '../common/GoogleDriveLogo.vue';
import { useDriveStore } from '../../stores/drive';
import { useUploadStore } from '../../stores/upload';
import { useAuthStore } from '../../stores/auth';

const props = defineProps({
  isOpen: Boolean,
});

const emit = defineEmits(['openCreateFolder', 'close']);

const drive = useDriveStore();
const uploadStore = useUploadStore();
const auth = useAuthStore();

const isNewMenuOpen = ref(false);
const fileInputRef = ref(null);

const quotaPercent = computed(() => {
  if (!auth.user?.storage_quota) return 0;
  return Math.min(100, Math.round((auth.user.storage_used / auth.user.storage_quota) * 100));
});

const canCreateNew = computed(() => {
  if (drive.currentSection === 'trash') return false;
  if (drive.currentSection === 'starred') {
    return !!drive.currentFolder && (drive.currentFolder.effective_role === 'editor' || drive.currentFolder.effective_role === 'owner');
  }
  if (drive.currentSection === 'shared') {
    return !!drive.currentFolder && (drive.currentFolder.effective_role === 'editor' || drive.currentFolder.effective_role === 'owner');
  }
  return true;
});

const selectSection = (section) => {
  emit('close');
  if (drive.currentSection === section && drive.currentFolder === null && !drive.searchQuery) return;
  drive.currentSection = section;
  drive.currentFolder = null;
  drive.breadcrumbs = [];
  drive.searchQuery = '';
  drive.fetchContents(null);
};

const triggerCreateFolder = () => {
  isNewMenuOpen.value = false;
  emit('close');
  emit('openCreateFolder');
};

const triggerFileUpload = () => {
  isNewMenuOpen.value = false;
  emit('close');
  fileInputRef.value?.click();
};

const handleFileSelected = (e) => {
  const files = Array.from(e.target.files || []);
  if (files.length > 0) {
    uploadStore.enqueueFiles(files, drive.currentFolder?.id);
  }
  e.target.value = '';
};

const formatBytes = (bytes) => {
  if (!bytes) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
};
</script>
