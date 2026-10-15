<template>
  <div
    v-if="uploadStore.isDrawerOpen && uploadStore.queue.length > 0"
    class="fixed bottom-0 left-0 right-0 sm:left-auto sm:right-8 z-40 w-full sm:w-96 bg-white rounded-t-2xl shadow-[0_8px_32px_rgba(0,0,0,0.22)] border border-gray-200 overflow-hidden flex flex-col transition-all duration-300 select-none"
    :class="uploadStore.isMinimized ? 'h-13' : 'max-h-[80vh] sm:max-h-[28rem]'"
  >
    <!-- Header -->
    <div
      class="flex items-center justify-between px-4 py-3 bg-[#202124] text-white cursor-pointer select-none"
      @click="uploadStore.isMinimized = !uploadStore.isMinimized"
    >
      <div class="flex items-center gap-2.5 text-sm font-medium">
        <!-- Spinner or Status Icon -->
        <svg
          v-if="activeCount > 0"
          class="animate-spin h-4 w-4 text-blue-400 shrink-0"
          xmlns="http://www.w3.org/2000/svg"
          fill="none"
          viewBox="0 0 24 24"
        >
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
        </svg>
        <AlertCircle v-else-if="failedCount > 0" class="w-4 h-4 text-rose-400 shrink-0" />
        <div v-else class="w-4 h-4 rounded-full bg-green-500/20 text-green-400 flex items-center justify-center shrink-0">
          <Check class="w-3 h-3 stroke-[3]" />
        </div>

        <span class="truncate">{{ headerTitle }}</span>
      </div>

      <div class="flex items-center gap-1">
        <!-- Minimize / Expand -->
        <button
          type="button"
          class="text-gray-300 hover:text-white p-1 rounded-full transition-colors hover:bg-white/10 cursor-pointer"
          :title="uploadStore.isMinimized ? 'Expand' : 'Minimize'"
          @click.stop="uploadStore.isMinimized = !uploadStore.isMinimized"
        >
          <ChevronUp v-if="uploadStore.isMinimized" class="w-4 h-4" />
          <ChevronDown v-else class="w-4 h-4" />
        </button>
        <!-- Close Drawer -->
        <button
          type="button"
          class="text-gray-300 hover:text-white p-1 rounded-full transition-colors hover:bg-white/10 cursor-pointer"
          title="Close"
          @click.stop="uploadStore.isDrawerOpen = false"
        >
          <X class="w-4 h-4" />
        </button>
      </div>
    </div>

    <!-- Uploads List -->
    <div v-show="!uploadStore.isMinimized" class="flex-1 overflow-y-auto divide-y divide-gray-100 bg-white">
      <div
        v-for="task in uploadStore.queue"
        :key="task.id"
        class="p-3.5 flex items-center gap-3 hover:bg-[#f8fafd] transition-colors"
      >
        <!-- File Icon -->
        <div class="w-8 h-8 flex items-center justify-center shrink-0">
          <FileIcon :mime-type="task.file?.type" size="md" />
        </div>

        <!-- Info & Progress -->
        <div class="flex-1 min-w-0 flex flex-col gap-1.5">
          <div class="flex items-center justify-between text-xs">
            <span class="font-medium text-[#1f1f1f] truncate" :title="task.name">
              {{ task.name }}
            </span>
          </div>

          <!-- Progress Bar -->
          <div class="w-full bg-[#e1e3e1] rounded-full h-1 overflow-hidden">
            <div
              class="h-full rounded-full transition-all duration-200"
              :class="{
                'bg-[#0b57d0]': task.status === 'uploading',
                'bg-amber-500': task.status === 'paused',
                'bg-blue-400 animate-pulse': task.status === 'processing',
                'bg-[#0f9d58]': task.status === 'completed',
                'bg-[#d93025]': task.status === 'failed',
                'bg-gray-400': task.status === 'cancelled',
              }"
              :style="{ width: `${task.progress}%` }"
            ></div>
          </div>

          <!-- Status and Speed line -->
          <div class="flex items-center justify-between text-[11px] text-[#747775]">
            <span>{{ formatBytes(task.size) }}</span>

            <span v-if="task.status === 'uploading'" class="font-mono text-[#444746] flex items-center gap-1">
              <span v-if="task.chunkStatus" class="text-blue-600 font-medium">[{{ task.chunkStatus }}]</span>
              <span>{{ task.speed || '0 KB/s' }} • {{ task.progress }}%</span>
            </span>
            <span v-else-if="task.status === 'paused'" class="text-amber-600 font-medium font-mono">
              Paused • {{ task.progress }}%
            </span>
            <span v-else-if="task.status === 'processing'" class="text-[#0b57d0] font-medium animate-pulse">
              Finalizing...
            </span>
            <span v-else-if="task.status === 'completed'" class="text-[#0f9d58] font-medium">
              Complete
            </span>
            <span v-else-if="task.status === 'failed'" class="text-[#d93025] font-medium truncate max-w-[140px]" :title="task.error">
              Failed
            </span>
            <span v-else-if="task.status === 'cancelled'" class="text-gray-500">
              Cancelled
            </span>
          </div>
        </div>

        <!-- Actions / Status Icons -->
        <div class="shrink-0 flex items-center gap-0.5">
          <!-- Pause while uploading -->
          <button
            v-if="task.status === 'uploading'"
            type="button"
            class="text-[#747775] hover:text-[#0b57d0] p-1.5 rounded-full hover:bg-black/5 transition-colors cursor-pointer"
            title="Pause upload"
            @click.stop="uploadStore.pauseUpload(task.id)"
          >
            <Pause class="w-3.5 h-3.5 fill-current" />
          </button>

          <!-- Resume when paused -->
          <button
            v-else-if="task.status === 'paused'"
            type="button"
            class="text-[#0b57d0] hover:text-[#0842a0] p-1.5 rounded-full hover:bg-blue-50 transition-colors cursor-pointer"
            title="Resume upload"
            @click.stop="uploadStore.resumeUpload(task.id)"
          >
            <Play class="w-3.5 h-3.5 fill-current" />
          </button>

          <!-- Cancel while uploading / processing / paused / pending -->
          <button
            v-if="task.status === 'uploading' || task.status === 'processing' || task.status === 'pending' || task.status === 'paused'"
            type="button"
            class="text-[#747775] hover:text-[#d93025] p-1.5 rounded-full hover:bg-black/5 transition-colors cursor-pointer"
            title="Cancel upload"
            @click.stop="uploadStore.cancelUpload(task.id)"
          >
            <X class="w-3.5 h-3.5" />
          </button>

          <!-- Completed Checkmark -->
          <div
            v-else-if="task.status === 'completed'"
            class="w-5 h-5 rounded-full bg-[#0f9d58]/15 text-[#0f9d58] flex items-center justify-center"
          >
            <Check class="w-3 h-3 stroke-[3]" />
          </div>

          <!-- Failed or Cancelled: Retry & Remove buttons -->
          <template v-else>
            <button
              type="button"
              class="text-[#747775] hover:text-[#0b57d0] p-1.5 rounded-full hover:bg-black/5 transition-colors cursor-pointer"
              title="Resume / Retry upload"
              @click.stop="uploadStore.retryUpload(task.id)"
            >
              <RotateCcw class="w-3.5 h-3.5" />
            </button>
            <button
              type="button"
              class="text-[#747775] hover:text-[#1f1f1f] p-1.5 rounded-full hover:bg-black/5 transition-colors cursor-pointer"
              title="Dismiss"
              @click.stop="uploadStore.removeTask(task.id)"
            >
              <X class="w-3.5 h-3.5" />
            </button>
          </template>
        </div>
      </div>
    </div>

    <!-- Footer with Clear Completed -->
    <div
      v-show="!uploadStore.isMinimized && finishedCount > 0"
      class="px-4 py-2 bg-[#f8fafd] border-t border-gray-150 flex items-center justify-between text-xs text-[#747775]"
    >
      <span>{{ finishedCount }} finished</span>
      <button
        type="button"
        class="text-[#0b57d0] hover:underline font-medium cursor-pointer"
        @click="uploadStore.clearCompleted"
      >
        Clear finished
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue';
import { ChevronUp, ChevronDown, Check, X, RotateCcw, AlertCircle, Pause, Play } from 'lucide-vue-next';
import { useUploadStore } from '../../stores/upload';
import FileIcon from '../drive/FileIcon.vue';

const uploadStore = useUploadStore();

const activeCount = computed(() => {
  return uploadStore.queue.filter(t => t.status === 'uploading' || t.status === 'processing' || t.status === 'pending').length;
});

const completedCount = computed(() => {
  return uploadStore.queue.filter(t => t.status === 'completed').length;
});

const failedCount = computed(() => {
  return uploadStore.queue.filter(t => t.status === 'failed').length;
});

const finishedCount = computed(() => {
  return uploadStore.queue.filter(t => t.status === 'completed' || t.status === 'cancelled' || t.status === 'failed').length;
});

const headerTitle = computed(() => {
  if (activeCount.value > 0) {
    const isProcessing = uploadStore.queue.some(t => t.status === 'processing');
    if (isProcessing && activeCount.value === 1) {
      return 'Processing 1 item...';
    }
    return `Uploading ${activeCount.value} item${activeCount.value > 1 ? 's' : ''}...`;
  }
  if (failedCount.value > 0) {
    if (completedCount.value > 0) {
      return `${completedCount.value} completed, ${failedCount.value} failed`;
    }
    return `${failedCount.value} upload${failedCount.value > 1 ? 's' : ''} failed`;
  }
  return `${completedCount.value} upload${completedCount.value > 1 ? 's' : ''} complete`;
});

const formatBytes = (bytes) => {
  if (!bytes) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
};
</script>
