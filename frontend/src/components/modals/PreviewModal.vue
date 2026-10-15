<template>
  <Transition name="fade">
    <div
      v-if="isOpen && file"
      class="fixed inset-0 z-50 flex flex-col bg-black/85 backdrop-blur-md p-2 sm:p-4 select-none"
    >
      <!-- Top Action Bar -->
      <div class="flex items-center justify-between text-white px-2 sm:px-4 py-2 border-b border-white/10 shrink-0 gap-2">
        <div class="flex items-center gap-2.5 sm:gap-3 min-w-0">
          <FileIcon :mime-type="file.mime_type" size="md" class="shrink-0" />
          <div class="truncate">
            <div class="text-xs sm:text-sm font-medium truncate max-w-[150px] xs:max-w-xs sm:max-w-md">{{ file.name }}</div>
            <div class="text-[10px] sm:text-xs text-gray-400">{{ formatBytes(file.size) }}</div>
          </div>
        </div>

        <div class="flex items-center gap-1.5 sm:gap-2 shrink-0">
          <button
            type="button"
            class="px-3 sm:px-4 py-1.5 sm:py-2 bg-white/10 hover:bg-white/20 rounded-full text-xs font-medium transition-colors flex items-center gap-1.5 sm:gap-2 cursor-pointer"
            @click="handleDownload"
          >
            <Download class="w-4 h-4" />
            <span class="hidden xs:inline">Download</span>
          </button>
          <button
            type="button"
            class="text-gray-300 hover:text-white p-1.5 sm:p-2 rounded-full hover:bg-white/10 transition-colors cursor-pointer"
            title="Close"
            @click="emit('close')"
          >
            <X class="w-5 h-5" />
          </button>
        </div>
      </div>

      <!-- Main Viewer Area -->
      <div class="flex-1 flex items-center justify-center p-3 sm:p-6 overflow-hidden">
        <!-- Loading State while obtaining media token -->
        <div v-if="isLoading" class="flex flex-col items-center gap-3 text-white">
          <div class="animate-spin rounded-full h-10 w-10 border-2 border-white border-t-transparent"></div>
          <span class="text-sm font-medium text-gray-300">Loading preview...</span>
        </div>

        <!-- Token fetch error -->
        <div v-else-if="loadError" class="text-center text-white flex flex-col items-center gap-4 animate-in fade-in">
          <div class="w-16 h-16 rounded-full bg-white/10 flex items-center justify-center text-amber-400">
            <AlertTriangle class="w-8 h-8" />
          </div>
          <div class="text-lg font-medium">Unable to load preview token</div>
          <button
            type="button"
            class="px-5 py-2 bg-[#0b57d0] hover:bg-[#0842a0] text-white rounded-full text-sm font-medium transition-colors cursor-pointer"
            @click="fetchToken"
          >
            Retry
          </button>
        </div>

        <!-- Video Player (with Range streaming & scrub) -->
        <video
          v-else-if="isVideo && streamUrl"
          controls
          autoplay
          class="max-h-full max-w-full rounded-2xl shadow-2xl bg-black"
          :src="streamUrl"
        ></video>

        <!-- Audio Player -->
        <div v-else-if="isAudio && streamUrl" class="bg-gray-900/90 p-5 sm:p-8 rounded-3xl shadow-2xl border border-gray-800 flex flex-col items-center gap-4 w-full max-w-sm sm:max-w-md">
          <div class="w-16 h-16 sm:w-20 sm:h-20 rounded-full bg-purple-500/20 text-purple-400 flex items-center justify-center">
            <Music class="w-8 h-8 sm:w-10 sm:h-10" />
          </div>
          <div class="text-white font-medium text-xs sm:text-sm truncate max-w-full text-center px-2">{{ file.name }}</div>
          <audio controls autoplay class="w-full max-w-xs sm:max-w-sm" :src="streamUrl"></audio>
        </div>

        <!-- Image Viewer -->
        <div v-else-if="isImage && streamUrl" class="max-h-full max-w-full flex items-center justify-center">
          <div v-if="imageError" class="text-center text-white flex flex-col items-center gap-4 animate-in fade-in">
            <div class="w-16 h-16 rounded-full bg-white/10 flex items-center justify-center text-amber-400">
              <AlertTriangle class="w-8 h-8" />
            </div>
            <div class="text-lg font-medium">Failed to display image</div>
            <p class="text-xs text-gray-400">The image could not be rendered or was interrupted</p>
            <div class="flex gap-2">
              <button
                type="button"
                class="px-4 py-2 bg-white/10 hover:bg-white/20 text-white rounded-full text-xs font-medium transition-colors cursor-pointer"
                @click="retryImage"
              >
                Retry
              </button>
              <button
                type="button"
                class="px-4 py-2 bg-[#0b57d0] hover:bg-[#0842a0] text-white rounded-full text-xs font-medium transition-colors cursor-pointer flex items-center gap-1.5"
                @click="handleDownload"
              >
                <Download class="w-3.5 h-3.5" />
                <span>Download</span>
              </button>
            </div>
          </div>
          <img
            v-show="!imageError"
            :key="imageKey"
            :src="streamUrl"
            :alt="file.name"
            class="max-h-full max-w-full object-contain rounded-2xl shadow-2xl"
            @error="imageError = true"
            @load="imageError = false"
          />
        </div>

        <!-- PDF Viewer: Desktop Native Viewer vs Mobile Options -->
        <template v-else-if="isPdf && streamUrl">
          <!-- Desktop (sm and larger): 100% Native High-Performance Browser PDF Viewer -->
          <iframe
            :src="streamUrl"
            class="hidden sm:block w-full h-full rounded-2xl bg-white border-0 shadow-2xl"
          ></iframe>

          <!-- Mobile (smaller than sm): Device Reader launcher + Inline Preview toggle -->
          <div class="sm:hidden w-full h-full flex flex-col items-center justify-center p-2">
            <!-- Inline Canvas Viewer if mobile user clicked 'Preview inline' -->
            <div v-if="mobilePdfMode === 'inline'" class="w-full h-full flex flex-col">
              <div class="flex justify-end pb-2">
                <button
                  type="button"
                  class="text-xs text-gray-300 hover:text-white px-3 py-1 bg-white/10 rounded-full cursor-pointer"
                  @click="mobilePdfMode = 'card'"
                >
                  ← Device options
                </button>
              </div>
              <div class="flex-1 min-h-0">
                <PdfViewer :stream-url="streamUrl" />
              </div>
            </div>

            <!-- Default Mobile PDF Card -->
            <div v-else class="flex flex-col items-center justify-center p-4 text-center max-w-sm w-full gap-4 animate-in fade-in">
              <div class="p-6 bg-white/10 rounded-3xl">
                <FileIcon :mime-type="file.mime_type" size="xl" />
              </div>
              <div>
                <div class="text-base font-medium text-white truncate max-w-xs">{{ file.name }}</div>
                <div class="text-xs text-gray-400 mt-1">{{ formatBytes(file.size) }} • PDF Document</div>
              </div>

              <!-- Open in Device Reader button -->
              <a
                :href="streamUrl"
                target="_blank"
                class="w-full py-3 bg-[#0b57d0] hover:bg-[#0842a0] text-white rounded-full text-sm font-medium transition-colors shadow-lg flex items-center justify-center gap-2 cursor-pointer"
              >
                <ExternalLink class="w-4 h-4" />
                <span>Open in Device Reader</span>
              </a>

              <!-- Preview inline button -->
              <button
                type="button"
                class="w-full py-2.5 bg-white/10 hover:bg-white/20 text-white rounded-full text-xs font-medium transition-colors cursor-pointer"
                @click="mobilePdfMode = 'inline'"
              >
                Preview inline in browser
              </button>

              <p class="text-[11px] text-gray-400 leading-relaxed">
                Large PDFs render fastest and smoothest using your device's built-in PDF viewer.
              </p>
            </div>
          </div>
        </template>

        <!-- Text & Code Viewer -->
        <CodeViewer
          v-else-if="isTextOrCode && streamUrl"
          :stream-url="streamUrl"
          :file-name="file.name"
        />

        <!-- Fallback Generic File -->
        <div v-else class="text-center text-white flex flex-col items-center gap-4 animate-in fade-in">
          <div class="p-6 bg-white/10 rounded-3xl">
            <FileIcon :mime-type="file.mime_type" size="xl" />
          </div>
          <div class="text-lg font-medium">No preview available for this file type</div>
          <p class="text-xs text-gray-400">Download the file to view it on your device</p>
          <button
            type="button"
            class="mt-2 px-6 py-2.5 bg-[#0b57d0] hover:bg-[#0842a0] text-white rounded-full text-sm font-medium transition-colors shadow-lg cursor-pointer flex items-center gap-2"
            @click="handleDownload"
          >
            <Download class="w-4 h-4" />
            <span>Download ({{ formatBytes(file.size) }})</span>
          </button>
        </div>
      </div>
    </div>
  </Transition>
</template>

<script setup>
import { ref, computed, watch } from 'vue';
import { Download, X, Music, AlertTriangle, ExternalLink } from 'lucide-vue-next';
import api from '../../services/api';
import FileIcon from '../drive/FileIcon.vue';
import PdfViewer from '../drive/PdfViewer.vue';
import CodeViewer from '../drive/CodeViewer.vue';

const props = defineProps({
  isOpen: Boolean,
  file: Object,
});
const emit = defineEmits(['close']);

const isLoading = ref(false);
const loadError = ref(false);
const mediaToken = ref('');
const mobilePdfMode = ref('card'); // 'card' | 'inline'
const imageError = ref(false);
const imageKey = ref(0);

const retryImage = () => {
  imageError.value = false;
  imageKey.value += 1;
};

const fetchToken = async () => {
  if (!props.isOpen || !props.file) return;
  isLoading.value = true;
  loadError.value = false;
  mediaToken.value = '';

  if (props.file.media_token) {
    mediaToken.value = props.file.media_token;
    isLoading.value = false;
    return;
  }

  try {
    const { data } = await api.get(`/drive/files/${props.file.id}/media_token/`);
    mediaToken.value = data.media_token;
  } catch (err) {
    loadError.value = true;
    mediaToken.value = '';
  } finally {
    isLoading.value = false;
  }
};

watch(
  [() => props.isOpen, () => props.file?.id],
  ([isOpen, fileId]) => {
    imageError.value = false;
    imageKey.value = 0;
    if (isOpen && fileId) {
      fetchToken();
    } else {
      mediaToken.value = '';
      isLoading.value = false;
      loadError.value = false;
    }
  },
  { immediate: true }
);

const streamUrl = computed(() => {
  if (!props.file || !mediaToken.value) return '';
  const baseURL = import.meta.env.VITE_API_URL || '/api';
  return `${baseURL}/drive/files/${props.file.id}/stream/?token=${encodeURIComponent(mediaToken.value)}`;
});

const handleDownload = async () => {
  if (!props.file) return;
  try {
    let token = mediaToken.value || props.file.media_token;
    if (!token) {
      const { data } = await api.get(`/drive/files/${props.file.id}/media_token/`);
      token = data.media_token;
    }
    const baseURL = import.meta.env.VITE_API_URL || '/api';
    const url = `${baseURL}/drive/files/${props.file.id}/stream/?token=${encodeURIComponent(token)}&download=1`;
    const a = document.createElement('a');
    a.href = url;
    a.download = props.file.name;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  } catch (err) {
    console.error('Download error:', err);
  }
};

const isVideo = computed(() => props.file?.mime_type?.startsWith('video/'));
const isAudio = computed(() => props.file?.mime_type?.startsWith('audio/'));
const isImage = computed(() => props.file?.mime_type?.startsWith('image/'));
const isPdf = computed(() => props.file?.mime_type === 'application/pdf');

const isTextOrCode = computed(() => {
  if (!props.file) return false;
  const mt = (props.file.mime_type || '').toLowerCase();
  if (
    mt.startsWith('text/') ||
    mt === 'application/json' ||
    mt === 'application/javascript' ||
    mt === 'application/xml' ||
    mt === 'application/x-sh'
  ) {
    return true;
  }
  const name = (props.file.name || '').toLowerCase();
  const textExts = [
    '.txt', '.md', '.json', '.js', '.jsx', '.ts', '.tsx', '.py',
    '.html', '.htm', '.css', '.scss', '.csv', '.log', '.env',
    '.xml', '.yml', '.yaml', '.sql', '.sh', '.bash', '.vue'
  ];
  return textExts.some(ext => name.endsWith(ext));
});

const formatBytes = (bytes) => {
  if (!bytes) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
};
</script>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
