<template>
  <div class="w-full h-full max-w-5xl flex flex-col bg-[#1e1e1e] rounded-2xl shadow-2xl border border-white/10 overflow-hidden select-text text-gray-200">
    <!-- Code Viewer Header Bar -->
    <div class="flex items-center justify-between px-4 py-2.5 bg-[#252526] border-b border-white/10 shrink-0 text-xs text-gray-300">
      <div class="flex items-center gap-2 truncate">
        <FileCode class="w-4 h-4 text-sky-400 shrink-0" />
        <span class="font-mono truncate">{{ fileName }}</span>
        <span class="text-gray-500">•</span>
        <span class="text-gray-400 font-mono">{{ lineCount }} lines</span>
      </div>

      <button
        type="button"
        class="flex items-center gap-1.5 px-3 py-1 bg-white/10 hover:bg-white/20 rounded-md transition-colors text-xs cursor-pointer text-white"
        @click="copyToClipboard"
      >
        <Check v-if="copied" class="w-3.5 h-3.5 text-emerald-400" />
        <Copy v-else class="w-3.5 h-3.5" />
        <span>{{ copied ? 'Copied!' : 'Copy' }}</span>
      </button>
    </div>

    <!-- Main Content Area with Line Numbers -->
    <div class="flex-1 overflow-auto flex text-xs sm:text-[13px] font-mono leading-relaxed p-2 sm:p-4 overscroll-contain">
      <!-- Loading State -->
      <div v-if="isLoading" class="flex items-center justify-center w-full py-20 text-gray-400 gap-2">
        <div class="animate-spin rounded-full h-5 w-5 border-2 border-sky-400 border-t-transparent"></div>
        <span>Loading text content...</span>
      </div>

      <!-- Error State -->
      <div v-else-if="error" class="flex flex-col items-center justify-center w-full py-20 text-red-400 gap-2">
        <span>Could not load text content</span>
        <button
          type="button"
          class="px-3 py-1 bg-white/10 hover:bg-white/20 rounded text-xs text-white cursor-pointer mt-2"
          @click="fetchContent"
        >
          Retry
        </button>
      </div>

      <!-- Content Display with Line Numbers -->
      <div v-else class="flex min-w-full">
        <!-- Line Numbers Column -->
        <div class="select-none text-right pr-4 text-gray-500 font-mono shrink-0 border-r border-white/10">
          <div v-for="n in lineCount" :key="n">{{ n }}</div>
        </div>

        <!-- Code Content -->
        <pre class="pl-4 text-gray-200 font-mono whitespace-pre overflow-x-auto flex-1"><code>{{ content }}</code></pre>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue';
import { FileCode, Copy, Check } from 'lucide-vue-next';
import axios from 'axios';

const props = defineProps({
  streamUrl: {
    type: String,
    required: true,
  },
  fileName: {
    type: String,
    default: 'file.txt',
  },
});

const content = ref('');
const isLoading = ref(true);
const error = ref(false);
const copied = ref(false);

const lineCount = computed(() => {
  if (!content.value) return 1;
  return content.value.split('\n').length;
});

const fetchContent = async () => {
  if (!props.streamUrl) return;
  isLoading.value = true;
  error.value = false;
  try {
    const res = await axios.get(props.streamUrl, {
      responseType: 'text',
      transformResponse: [(data) => data], // Don't JSON.parse automatically
    });
    content.value = typeof res.data === 'string' ? res.data : JSON.stringify(res.data, null, 2);
  } catch (err) {
    console.error('Fetch text error:', err);
    error.value = true;
  } finally {
    isLoading.value = false;
  }
};

const copyToClipboard = async () => {
  if (!content.value) return;
  try {
    await navigator.clipboard.writeText(content.value);
    copied.value = true;
    setTimeout(() => {
      copied.value = false;
    }, 2000);
  } catch (err) {
    console.error('Clipboard error:', err);
  }
};

watch(
  () => props.streamUrl,
  () => {
    fetchContent();
  }
);

onMounted(() => {
  fetchContent();
});
</script>
