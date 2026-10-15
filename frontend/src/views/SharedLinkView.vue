<template>
  <div class="h-screen h-[100dvh] w-full max-w-[100vw] flex flex-col bg-drive-bg text-[#1f1f1f] select-none font-sans overflow-hidden">
    <!-- Instant File Preview Mode: Fullscreen Dark Google Drive Style -->
    <div
      v-if="shareData?.file && !needsPassword && !loading"
      class="fixed inset-0 z-40 flex flex-col bg-[#111315] text-white"
    >
      <!-- Top Action Bar -->
      <header class="h-16 flex items-center justify-between px-3 sm:px-6 bg-black/40 backdrop-blur-md border-b border-white/10 shrink-0 gap-2">
        <div class="flex items-center gap-2 sm:gap-4 min-w-0">
          <router-link to="/" class="hover:opacity-80 transition-opacity shrink-0" title="Go to Drive">
            <GoogleDriveLogo :size="30" />
          </router-link>
          <div class="h-4 sm:h-5 w-px bg-white/20 shrink-0"></div>
          <div class="flex items-center gap-2 sm:gap-2.5 truncate min-w-0">
            <FileIcon :mime-type="shareData.file.mime_type" size="sm" class="shrink-0" />
            <div class="truncate">
              <span class="text-xs sm:text-sm font-medium text-white truncate block max-w-[130px] xs:max-w-xs sm:max-w-md">{{ shareData.file.name }}</span>
              <span class="text-[10px] sm:text-[11px] text-gray-400 block truncate">
                {{ formatBytes(shareData.file.size) }}
                <template v-if="formatUserDisplay(shareData.file).name">
                  • Shared by {{ formatUserDisplay(shareData.file).name }}
                </template>
              </span>
            </div>
          </div>
        </div>

        <div class="flex items-center gap-1.5 sm:gap-3 shrink-0">
          <a
            :href="downloadUrl"
            download
            class="px-3 sm:px-5 py-1.5 sm:py-2 bg-[#0b57d0] hover:bg-[#0842a0] text-white rounded-full text-xs font-medium transition-all shadow-md flex items-center gap-1.5 sm:gap-2 cursor-pointer"
          >
            <Download class="w-4 h-4" />
            <span class="hidden xs:inline">Download</span>
          </a>

          <router-link
            v-if="!auth.isAuthenticated"
            :to="'/login?redirect=' + encodeURIComponent(route.fullPath)"
            class="px-3 sm:px-5 py-1.5 sm:py-2 text-xs font-medium text-white/90 border border-white/20 rounded-full hover:bg-white/10 transition-colors"
          >
            Sign in
          </router-link>
          <router-link
            v-else
            to="/"
            class="px-3 sm:px-5 py-1.5 sm:py-2 text-xs font-medium text-white/90 border border-white/20 rounded-full hover:bg-white/10 transition-colors"
          >
            My Drive
          </router-link>
        </div>
      </header>

      <!-- Main Viewer Body -->
      <main class="flex-1 flex items-center justify-center p-3 sm:p-6 overflow-hidden relative">
        <!-- Video Player (Seeking with RFC 9110 Range stream) -->
        <video
          v-if="isVideo(shareData.file) && streamUrl"
          controls
          autoplay
          class="max-h-full max-w-full rounded-2xl shadow-2xl bg-black"
          :src="streamUrl"
        ></video>

        <!-- Audio Player -->
        <div
          v-else-if="isAudio(shareData.file) && streamUrl"
          class="bg-gray-900/95 p-5 sm:p-8 rounded-3xl shadow-2xl border border-gray-800 flex flex-col items-center gap-4 text-center w-full max-w-sm sm:max-w-md"
        >
          <div class="w-16 h-16 sm:w-20 sm:h-20 rounded-full bg-purple-500/20 text-purple-400 flex items-center justify-center">
            <Music class="w-8 h-8 sm:w-10 sm:h-10" />
          </div>
          <div class="text-white font-medium text-xs sm:text-sm truncate max-w-full text-center px-2">{{ shareData.file.name }}</div>
          <audio controls autoplay class="w-full max-w-xs sm:max-w-sm" :src="streamUrl"></audio>
        </div>

        <!-- Image Viewer -->
        <img
          v-else-if="isImage(shareData.file) && streamUrl"
          :src="streamUrl"
          :alt="shareData.file.name"
          class="max-h-full max-w-full object-contain rounded-2xl shadow-2xl"
        />

        <!-- PDF Viewer -->
        <iframe
          v-else-if="isPdf(shareData.file) && streamUrl"
          :src="streamUrl"
          class="w-full h-full rounded-2xl bg-white border-0 shadow-2xl"
        ></iframe>

        <!-- Fallback Generic File Card -->
        <div v-else class="text-center text-white flex flex-col items-center gap-4 animate-in fade-in">
          <div class="p-6 bg-white/10 rounded-3xl">
            <FileIcon :mime-type="shareData.file.mime_type" size="xl" />
          </div>
          <div class="text-lg font-medium">No preview available</div>
          <p class="text-xs text-gray-400">Download the file to view it on your device</p>
          <a
            :href="downloadUrl"
            download
            class="mt-2 px-6 py-2.5 bg-[#0b57d0] hover:bg-[#0842a0] text-white rounded-full text-sm font-medium transition-colors shadow-lg cursor-pointer flex items-center gap-2"
          >
            <Download class="w-4 h-4" />
            <span>Download ({{ formatBytes(shareData.file.size) }})</span>
          </a>
        </div>
      </main>
    </div>

    <!-- Standard Google Drive Layout for Folder Sharing & Password / Loading states -->
    <template v-else>
      <!-- Navbar -->
      <header class="h-16 flex items-center justify-between px-3 sm:px-8 bg-white border-b border-gray-200/80 shrink-0 gap-2">
        <div class="flex items-center gap-2 sm:gap-3 min-w-0">
          <router-link to="/" class="hover:opacity-80 transition-opacity shrink-0">
            <GoogleDriveLogo :size="32" />
          </router-link>
          <span class="text-base sm:text-xl font-normal text-[#444746] tracking-tight truncate">Shared with you</span>
        </div>

        <div class="flex items-center gap-2 sm:gap-3 shrink-0">
          <router-link
            v-if="!auth.isAuthenticated"
            :to="'/login?redirect=' + encodeURIComponent(route.fullPath)"
            class="px-3 sm:px-5 py-1.5 sm:py-2 text-xs sm:text-sm font-medium text-[#0b57d0] border border-gray-300 rounded-full hover:bg-[#edf2fc] transition-colors"
          >
            Sign in
          </router-link>
          <router-link
            v-else
            to="/"
            class="px-3 sm:px-5 py-1.5 sm:py-2 text-xs sm:text-sm font-medium text-[#0b57d0] border border-gray-300 rounded-full hover:bg-[#edf2fc] transition-colors"
          >
            My Drive
          </router-link>
        </div>
      </header>

      <!-- Main Content -->
      <main class="flex-1 min-h-0 w-full overflow-y-auto overscroll-contain">
        <div class="max-w-6xl w-full mx-auto p-3 sm:p-6 pb-28 sm:pb-36 flex flex-col min-h-full">
          <!-- Loading State -->
        <div v-if="loading" class="flex flex-col items-center justify-center py-24 gap-3 my-auto">
          <div class="animate-spin rounded-full h-8 w-8 border-2 border-[#0b57d0] border-t-transparent"></div>
          <span class="text-xs font-medium text-[#747775]">Loading shared content...</span>
        </div>

        <!-- Password Prompt State -->
        <div
          v-else-if="needsPassword"
          class="bg-white rounded-[28px] shadow-[0_8px_32px_rgba(0,0,0,0.12)] max-w-md w-full mx-auto p-8 border border-gray-150 flex flex-col gap-4 text-center animate-in fade-in zoom-in-95 my-auto"
        >
          <div class="w-14 h-14 rounded-full bg-[#f8fafd] text-[#0b57d0] border border-[#c2e7ff] flex items-center justify-center mx-auto mb-1">
            <Lock class="w-6 h-6" />
          </div>
          <h3 class="text-xl font-medium text-[#1f1f1f]">This link is password protected</h3>
          <p class="text-xs text-[#747775]">Please enter the password provided by the owner to access this item.</p>

          <form @submit.prevent="fetchSharedData(currentFolderId)" class="flex flex-col gap-3 mt-2">
            <input
              v-model="password"
              type="password"
              placeholder="Enter password"
              required
              class="px-4 py-3 rounded-xl border border-gray-300 text-sm focus:outline-none focus:border-[#0b57d0] focus:ring-2 focus:ring-[#0b57d0]/20"
            />
            <button
              type="submit"
              class="py-3 bg-[#0b57d0] hover:bg-[#0842a0] text-white rounded-full font-medium text-sm transition-all shadow-xs cursor-pointer"
            >
              Access Item
            </button>
          </form>
        </div>

        <!-- Shared Folder View (Google Drive Parity: Breadcrumbs, Subfolders, Files, Double-click Preview) -->
        <div
          v-else-if="shareData?.folder"
          class="flex flex-col gap-6"
        >
          <!-- Breadcrumbs Bar -->
          <div class="flex items-center justify-between py-2 border-b border-gray-200/80">
            <div class="flex items-center gap-1 text-[#1f1f1f] overflow-x-auto select-none">
              <template v-for="(crumb, index) in shareData.breadcrumbs" :key="crumb.id">
                <button
                  type="button"
                  :class="[
                    'px-3 py-1.5 rounded-full text-lg font-normal transition-colors flex items-center gap-2 cursor-pointer',
                    index === shareData.breadcrumbs.length - 1
                      ? 'text-[#1f1f1f] font-medium'
                      : 'text-[#444746] hover:bg-black/5'
                  ]"
                  @click="navigateToFolder(crumb.id)"
                >
                  <FileIcon :is-folder="true" size="sm" />
                  <span>{{ crumb.name }}</span>
                </button>
                <ChevronRight
                  v-if="index < shareData.breadcrumbs.length - 1"
                  class="w-4 h-4 text-[#747775] shrink-0"
                />
              </template>
            </div>
            <div v-if="formatUserDisplay(shareData.folder).name" class="text-xs text-[#747775] shrink-0 pl-3">
              Shared by <span class="font-medium text-[#1f1f1f]">{{ formatUserDisplay(shareData.folder).name }}</span>
            </div>
          </div>

          <!-- Subfolders Section -->
          <div v-if="shareData.subfolders?.length > 0">
            <div class="flex items-center justify-between mb-3 px-1">
              <h3 class="text-sm font-medium text-[#444746]">Folders</h3>
              <span class="text-xs text-[#747775]">{{ shareData.subfolders.length }}</span>
            </div>

            <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3">
              <div
                v-for="subfolder in shareData.subfolders"
                :key="subfolder.id"
                class="flex items-center justify-between px-3.5 py-3 bg-white hover:bg-[#edf2fc] rounded-xl border border-gray-200/80 cursor-pointer transition-all duration-150 group shadow-xs hover:border-[#c2e7ff]"
                @click="navigateToFolder(subfolder.id)"
                :title="'Click to open ' + subfolder.name"
              >
                <div class="flex items-center gap-3 truncate min-w-0">
                  <FileIcon :is-folder="true" size="sm" />
                  <span class="text-sm font-medium text-[#1f1f1f] truncate">{{ subfolder.name }}</span>
                </div>
                <ChevronRight class="w-4 h-4 text-gray-400 group-hover:text-[#0b57d0] transition-colors shrink-0" />
              </div>
            </div>
          </div>

          <!-- Files Section -->
          <div v-if="shareData.files?.length > 0">
            <div class="flex items-center justify-between mb-3 px-1">
              <h3 class="text-sm font-medium text-[#444746]">Files</h3>
              <span class="text-xs text-[#747775]">{{ shareData.files.length }}</span>
            </div>

            <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
              <div
                v-for="subfile in shareData.files"
                :key="subfile.id"
                class="flex flex-col bg-white rounded-2xl border border-gray-200/80 overflow-hidden cursor-pointer hover:border-[#c2e7ff] hover:shadow-[0_1px_3px_0_rgba(60,64,67,0.3),0_4px_8px_3px_rgba(60,64,67,0.15)] transition-all duration-200 group"
                @dblclick="openFilePreview(subfile)"
                :title="'Double-click to preview ' + subfile.name"
              >
                <!-- Thumbnail / Canvas Area -->
                <div class="h-32 bg-[#f0f4f9] group-hover:bg-[#e9eef6] flex items-center justify-center p-6 border-b border-gray-100 transition-colors relative">
                  <FileIcon :mime-type="subfile.mime_type" size="xl" />
                </div>

                <!-- Card Meta & Action -->
                <div class="p-3.5 flex items-center justify-between gap-2">
                  <div class="flex items-center gap-2 truncate flex-1 min-w-0">
                    <FileIcon :mime-type="subfile.mime_type" size="sm" class="shrink-0" />
                    <div class="truncate">
                      <div class="text-[13px] font-medium text-[#1f1f1f] truncate" :title="subfile.name">
                        {{ subfile.name }}
                      </div>
                      <div class="text-[11px] text-[#747775] mt-0.5">
                        {{ formatBytes(subfile.size) }}
                      </div>
                    </div>
                  </div>

                  <button
                    type="button"
                    class="p-1.5 text-gray-400 hover:text-[#0b57d0] hover:bg-[#edf2fc] rounded-full transition-colors cursor-pointer shrink-0"
                    title="Download file"
                    @click.stop="downloadSubfile(subfile)"
                  >
                    <Download class="w-4 h-4" />
                  </button>
                </div>
              </div>
            </div>
          </div>

          <!-- Empty Shared Folder State -->
          <div
            v-if="(!shareData.subfolders || shareData.subfolders.length === 0) && (!shareData.files || shareData.files.length === 0)"
            class="flex flex-col items-center justify-center py-20 text-center select-none"
          >
            <div class="w-20 h-20 rounded-full bg-gray-100 text-gray-400 flex items-center justify-center mb-3">
              <FileIcon :is-folder="true" size="lg" />
            </div>
            <p class="text-base font-medium text-[#1f1f1f]">This folder is empty</p>
            <p class="text-xs text-[#747775] mt-1">No subfolders or files have been shared here yet</p>
          </div>
        </div>
      </div>
    </main>
    </template>

    <!-- Preview Modal for Folder Browsing -->
    <PreviewModal
      :is-open="isPreviewOpen"
      :file="activePreviewFile"
      @close="isPreviewOpen = false"
    />

    <ToastContainer />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue';
import { useRoute } from 'vue-router';
import axios from 'axios';
import { Lock, Download, ChevronRight, Music } from 'lucide-vue-next';
import GoogleDriveLogo from '../components/common/GoogleDriveLogo.vue';
import FileIcon from '../components/drive/FileIcon.vue';
import PreviewModal from '../components/modals/PreviewModal.vue';
import ToastContainer from '../components/feedback/ToastContainer.vue';
import { useFeedbackStore } from '../stores/feedback';
import { useAuthStore } from '../stores/auth';
import { formatUserDisplay } from '../utils/user';

const route = useRoute();
const feedback = useFeedbackStore();
const auth = useAuthStore();

const token = route.params.token;
const loading = ref(true);
const needsPassword = ref(false);
const password = ref('');
const shareData = ref(null);
const currentFolderId = ref(null);

const isPreviewOpen = ref(false);
const activePreviewFile = ref(null);

const baseURL = import.meta.env.VITE_API_URL || '/api';

const downloadUrl = computed(() => {
  if (!shareData.value?.file) return '';
  const tokenParam = shareData.value.media_token ? `?token=${encodeURIComponent(shareData.value.media_token)}&download=1` : '?download=1';
  return `${baseURL}/drive/files/${shareData.value.file.id}/stream/${tokenParam}`;
});

const streamUrl = computed(() => {
  if (!shareData.value?.file) return '';
  const tokenParam = shareData.value.media_token ? `?token=${encodeURIComponent(shareData.value.media_token)}` : '';
  return `${baseURL}/drive/files/${shareData.value.file.id}/stream/${tokenParam}`;
});

const isVideo = (file) => file?.mime_type?.startsWith('video/');
const isAudio = (file) => file?.mime_type?.startsWith('audio/');
const isImage = (file) => file?.mime_type?.startsWith('image/');
const isPdf = (file) => file?.mime_type === 'application/pdf';

const openFilePreview = (file) => {
  activePreviewFile.value = { ...file };
  isPreviewOpen.value = true;
};

const downloadSubfile = (subfile) => {
  if (!subfile) return;
  const tokenParam = subfile.media_token ? `?token=${encodeURIComponent(subfile.media_token)}&download=1` : '?download=1';
  const url = `${baseURL}/drive/files/${subfile.id}/stream/${tokenParam}`;
  const a = document.createElement('a');
  a.href = url;
  a.download = subfile.name;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
};

const navigateToFolder = (folderId) => {
  currentFolderId.value = folderId;
  fetchSharedData(folderId);
};

const fetchSharedData = async (folderId = null) => {
  loading.value = true;
  needsPassword.value = false;
  try {
    const params = {};
    if (password.value) params.password = password.value;
    if (folderId) params.folder = folderId;

    const { data } = await axios.get(`${baseURL}/drive/shares/public/${token}/`, { params });
    shareData.value = data;
    if (data.current_folder) {
      currentFolderId.value = data.current_folder.id;
    }
  } catch (err) {
    if (err.response?.status === 403 && err.response?.data?.error?.includes('Password')) {
      needsPassword.value = true;
    } else {
      feedback.showToast('error', err.response?.data?.detail || err.response?.data?.error || 'Invalid or expired share link');
    }
  } finally {
    loading.value = false;
  }
};

const formatBytes = (bytes) => {
  if (!bytes) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
};

onMounted(() => {
  fetchSharedData();
});
</script>
