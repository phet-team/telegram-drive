<template>
  <header class="h-16 flex items-center justify-between px-3 sm:px-5 bg-drive-bg border-b border-drive-border shrink-0 select-none">
    <!-- Left: Hamburger (Mobile) + Google Drive Logo & Brand -->
    <div class="flex items-center gap-1.5 sm:gap-2.5 w-auto lg:w-64 shrink-0">
      <!-- Hamburger Menu for Mobile/Tablet -->
      <button
        type="button"
        class="lg:hidden text-[#444746] hover:text-[#1f1f1f] p-2 rounded-full hover:bg-black/5 transition-colors cursor-pointer mr-0.5"
        title="Main menu"
        @click="emit('toggleSidebar')"
      >
        <Menu class="w-5 h-5" />
      </button>

      <GoogleDriveLogo :size="36" class="shrink-0" />
      <span class="text-[20px] sm:text-[22px] text-[#444746] font-normal tracking-tight font-sans">
        Drive
      </span>
      <span class="hidden sm:inline-block ml-1 text-[10px] font-semibold text-[#0b57d0] bg-[#d3e3fd]/60 px-2 py-0.5 rounded-full uppercase tracking-wider">
        Telegram
      </span>
    </div>

    <!-- Center: Google Drive Search Bar -->
    <div class="flex-1 max-w-2xl px-2 sm:px-4">
      <div
        class="relative flex items-center bg-[#edf2fc] hover:bg-[#e4ebf7] focus-within:bg-white focus-within:shadow-[0_1px_3px_0_rgba(60,64,67,0.3),0_4px_8px_3px_rgba(60,64,67,0.15)] transition-all rounded-full h-10 sm:h-11 px-3 sm:px-4 border border-transparent"
      >
        <Search class="w-4 h-4 sm:w-5 sm:h-5 text-[#444746] mr-2 sm:mr-3 shrink-0" />
        <input
          :value="drive.searchQuery"
          @input="drive.setSearchQuery($event.target.value)"
          @keydown.enter="drive.fetchContents(drive.currentFolder?.id)"
          @keydown.esc="drive.clearSearch()"
          type="text"
          placeholder="Search in Drive"
          class="w-full bg-transparent border-0 focus:outline-none text-[14px] sm:text-[15px] text-[#1f1f1f] placeholder-[#444746]"
        />
        <button
          v-if="drive.searchQuery"
          type="button"
          class="text-[#444746] hover:text-[#1f1f1f] hover:bg-black/5 p-1 rounded-full transition-colors ml-1 cursor-pointer"
          title="Clear search"
          @click="drive.clearSearch()"
        >
          <X class="w-4 h-4" />
        </button>
      </div>
    </div>

    <!-- Right: Quick actions & Account Profile -->
    <div class="flex items-center gap-1 sm:gap-2 shrink-0">
      <!-- Help button (hidden on mobile) -->
      <button
        type="button"
        class="hidden sm:flex text-[#444746] hover:text-[#1f1f1f] hover:bg-[#eaebef] p-2.5 rounded-full transition-colors"
        title="Help & Info"
        @click="showHelpToast"
      >
        <HelpCircle class="w-5 h-5" />
      </button>

      <!-- Account Profile Dropdown -->
      <div class="relative ml-1" ref="dropdownRef">
        <button
          type="button"
          class="flex items-center p-1 rounded-full hover:ring-4 hover:ring-black/5 transition-all cursor-pointer"
          @click="isDropdownOpen = !isDropdownOpen"
        >
          <img
            v-if="auth.user?.avatar_url"
            :src="auth.user.avatar_url"
            class="w-8 h-8 rounded-full object-cover border border-gray-200"
          />
          <div
            v-else
            class="w-8 h-8 rounded-full bg-[#0b57d0] text-white flex items-center justify-center font-medium text-sm shadow-sm"
          >
            {{ userInitial }}
          </div>
        </button>

        <!-- Google Workspace Account Popover -->
        <div
          v-if="isDropdownOpen"
          class="absolute right-0 mt-2 w-80 max-w-[calc(100vw-24px)] bg-white rounded-3xl shadow-[0_4px_24px_rgba(0,0,0,0.18)] border border-gray-150 p-5 z-50 select-none animate-in fade-in zoom-in-95 duration-150"
        >
          <!-- User Info Card -->
          <div class="flex flex-col items-center text-center pb-4 border-b border-gray-100">
            <img
              v-if="auth.user?.avatar_url"
              :src="auth.user.avatar_url"
              class="w-16 h-16 rounded-full object-cover border border-gray-200 mb-2.5 shadow-sm"
            />
            <div
              v-else
              class="w-16 h-16 rounded-full bg-[#0b57d0] text-white flex items-center justify-center font-medium text-2xl mb-2.5 shadow-sm"
            >
              {{ userInitial }}
            </div>
            <div class="font-medium text-[#1f1f1f] text-base truncate max-w-[240px]">
              {{ auth.user?.name || 'User' }}
            </div>
            <div class="text-xs text-[#444746] truncate max-w-[240px] mt-0.5">
              {{ displayIdentifier }}
            </div>
          </div>

          <!-- Storage Breakdown -->
          <div class="py-4 border-b border-gray-100 flex flex-col gap-2">
            <div class="flex items-center justify-between text-xs text-[#444746]">
              <span class="font-medium">Cloud Storage</span>
              <span v-if="auth.user?.storage_quota">{{ formatBytes(auth.user?.storage_used) }} of {{ formatBytes(auth.user?.storage_quota) }}</span>
              <span v-else>{{ formatBytes(auth.user?.storage_used) }} (Unlimited)</span>
            </div>
            <div class="w-full bg-[#e1e3e1] rounded-full h-1 overflow-hidden">
              <div
                class="bg-[#0b57d0] h-full rounded-full transition-all duration-300"
                :style="{ width: auth.user?.storage_quota ? `${quotaPercent}%` : '100%' }"
              ></div>
            </div>
          </div>

          <!-- Actions -->
          <div class="pt-3">
            <button
              type="button"
              class="w-full py-2.5 px-4 text-[#d93025] hover:bg-red-50/80 rounded-full flex items-center justify-center gap-2 font-medium text-sm transition-colors cursor-pointer"
              @click="handleLogout"
            >
              <LogOut class="w-4 h-4" />
              <span>Sign out</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  </header>
</template>

<script setup>
import { ref, computed } from 'vue';
import { Search, X, HelpCircle, LogOut, Menu } from 'lucide-vue-next';
import GoogleDriveLogo from '../common/GoogleDriveLogo.vue';
import { useAuthStore } from '../../stores/auth';
import { useDriveStore } from '../../stores/drive';
import { useFeedbackStore } from '../../stores/feedback';

const emit = defineEmits(['toggleSidebar']);

const auth = useAuthStore();
const drive = useDriveStore();
const feedback = useFeedbackStore();
const isDropdownOpen = ref(false);

const userInitial = computed(() => {
  return (auth.user?.name?.[0] || auth.user?.email?.[0] || 'U').toUpperCase();
});

const displayIdentifier = computed(() => {
  const email = auth.user?.email || '';
  if (email.endsWith('@telegram.user') && auth.user?.telegram_id) {
    return `Telegram ID: ${auth.user.telegram_id}`;
  }
  return email;
});

const quotaPercent = computed(() => {
  if (!auth.user?.storage_quota) return 0;
  return Math.min(100, Math.round((auth.user.storage_used / auth.user.storage_quota) * 100));
});

const formatBytes = (bytes) => {
  if (!bytes) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
};

const showHelpToast = () => {
  feedback.showToast('info', 'Telegram Storage Engine is connected via MTProto with 2GB single-file support.');
};

const handleLogout = () => {
  isDropdownOpen.value = false;
  auth.logout();
};
</script>
