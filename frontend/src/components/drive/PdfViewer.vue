<template>
  <div class="relative w-full h-full flex flex-col items-center justify-between overflow-hidden select-none">
    <!-- Controls Toolbar (Floating Pill) -->
    <div
      class="z-20 mb-2 flex items-center gap-1.5 sm:gap-3 bg-[#202124]/90 backdrop-blur-md px-3 sm:px-4 py-1.5 rounded-full border border-white/10 shadow-xl text-white text-xs sm:text-sm"
    >
      <button
        type="button"
        :disabled="currentPage <= 1 || isLoading"
        class="p-1 rounded-full hover:bg-white/20 disabled:opacity-30 disabled:hover:bg-transparent cursor-pointer transition-colors"
        title="Previous page"
        @click="prevPage"
      >
        <ChevronLeft class="w-4 h-4 sm:w-5 sm:h-5" />
      </button>

      <span class="font-mono text-xs sm:text-sm px-1">
        {{ currentPage }} / {{ totalPages || 1 }}
      </span>

      <button
        type="button"
        :disabled="currentPage >= totalPages || isLoading"
        class="p-1 rounded-full hover:bg-white/20 disabled:opacity-30 disabled:hover:bg-transparent cursor-pointer transition-colors"
        title="Next page"
        @click="nextPage"
      >
        <ChevronRight class="w-4 h-4 sm:w-5 sm:h-5" />
      </button>

      <div class="h-4 w-px bg-white/20 mx-1"></div>

      <button
        type="button"
        :disabled="scale <= 0.5 || isLoading"
        class="p-1 rounded-full hover:bg-white/20 disabled:opacity-30 cursor-pointer transition-colors"
        title="Zoom out"
        @click="zoomOut"
      >
        <ZoomOut class="w-4 h-4" />
      </button>

      <span class="font-mono text-[11px] sm:text-xs text-gray-300 w-10 text-center">
        {{ Math.round(scale * 100) }}%
      </span>

      <button
        type="button"
        :disabled="scale >= 3.0 || isLoading"
        class="p-1 rounded-full hover:bg-white/20 disabled:opacity-30 cursor-pointer transition-colors"
        title="Zoom in"
        @click="zoomIn"
      >
        <ZoomIn class="w-4 h-4" />
      </button>
    </div>

    <!-- Main Scrollable Canvas Area -->
    <div
      ref="containerRef"
      class="flex-1 w-full overflow-auto flex items-center justify-center p-2 sm:p-4 overscroll-contain"
      @touchstart="handleTouchStart"
      @touchend="handleTouchEnd"
    >
      <!-- Loading Spinner with Progress -->
      <div v-if="isLoading" class="flex flex-col items-center gap-3 text-white my-auto">
        <div class="animate-spin rounded-full h-9 w-9 border-2 border-[#0b57d0] border-t-transparent"></div>
        <span class="text-xs text-gray-300">
          {{ downloadProgress > 0 && downloadProgress < 100 ? `Loading document ${downloadProgress}%` : 'Rendering document...' }}
        </span>
      </div>

      <!-- Error State -->
      <div v-else-if="loadError" class="text-center text-white my-auto">
        <p class="text-sm font-medium text-amber-400">Failed to render PDF</p>
        <button
          type="button"
          class="mt-3 px-4 py-1.5 bg-[#0b57d0] rounded-full text-xs cursor-pointer hover:bg-[#0842a0]"
          @click="renderPage(currentPage)"
        >
          Retry
        </button>
      </div>

      <!-- Canvas Element -->
      <canvas
        v-show="!isLoading && !loadError"
        ref="canvasRef"
        class="shadow-2xl rounded-lg bg-white max-w-full transition-transform duration-100"
      ></canvas>
    </div>
  </div>
</template>

<script setup>
import { shallowRef, ref, markRaw, onMounted, onUnmounted, watch } from 'vue';
import { ChevronLeft, ChevronRight, ZoomIn, ZoomOut } from 'lucide-vue-next';
import * as pdfjsLib from 'pdfjs-dist';
import pdfWorker from 'pdfjs-dist/build/pdf.worker.mjs?url';

pdfjsLib.GlobalWorkerOptions.workerSrc = pdfWorker;

const props = defineProps({
  streamUrl: {
    type: String,
    required: true,
  },
});

const containerRef = ref(null);
const canvasRef = ref(null);
const pdfDoc = shallowRef(null);
const currentPage = ref(1);
const totalPages = ref(0);
const scale = ref(1.0);
const isLoading = ref(true);
const loadError = ref(false);
const downloadProgress = ref(0);

let currentLoadingTask = null;
let currentRenderTask = null;
let touchStartX = 0;

const handleTouchStart = (e) => {
  touchStartX = e.changedTouches[0].clientX;
};

const handleTouchEnd = (e) => {
  const touchEndX = e.changedTouches[0].clientX;
  const diffX = touchEndX - touchStartX;
  // Swipe threshold 60px
  if (Math.abs(diffX) > 60) {
    if (diffX < 0) {
      nextPage(); // swipe left -> next page
    } else {
      prevPage(); // swipe right -> prev page
    }
  }
};

const loadPdf = async () => {
  if (!props.streamUrl) return;
  isLoading.value = true;
  loadError.value = false;
  downloadProgress.value = 0;

  // Cancel any ongoing render task before loading new document
  if (currentRenderTask) {
    currentRenderTask.cancel();
    currentRenderTask = null;
  }
  if (currentLoadingTask) {
    try {
      currentLoadingTask.destroy();
    } catch (e) {}
    currentLoadingTask = null;
  }

  try {
    currentLoadingTask = pdfjsLib.getDocument({
      url: props.streamUrl,
      withCredentials: false,
      disableRange: true,
      disableStream: true,
    });

    currentLoadingTask.onProgress = ({ loaded, total }) => {
      if (total > 0) {
        downloadProgress.value = Math.min(100, Math.round((loaded / total) * 100));
      }
    };

    const doc = await currentLoadingTask.promise;
    pdfDoc.value = markRaw(doc);
    totalPages.value = doc.numPages;
    currentPage.value = 1;

    // Auto calculate initial scale to fit mobile screen width
    if (containerRef.value) {
      const containerWidth = containerRef.value.clientWidth - 32;
      const firstPage = await doc.getPage(1);
      const viewport = firstPage.getViewport({ scale: 1.0 });
      if (viewport.width > containerWidth) {
        scale.value = Math.max(0.6, Math.min(1.0, containerWidth / viewport.width));
      } else {
        scale.value = 1.0;
      }
    }

    await renderPage(currentPage.value);
  } catch (err) {
    console.error('PDF load error:', err);
    loadError.value = true;
  } finally {
    isLoading.value = false;
  }
};

const renderPage = async (pageNumber) => {
  if (!pdfDoc.value || !canvasRef.value) return;
  isLoading.value = true;
  loadError.value = false;

  // Cancel prior page rendering to avoid canvas collision
  if (currentRenderTask) {
    currentRenderTask.cancel();
    currentRenderTask = null;
  }

  try {
    const page = await pdfDoc.value.getPage(pageNumber);
    const viewport = page.getViewport({ scale: scale.value });

    const canvas = canvasRef.value;
    if (!canvas) return;
    const context = canvas.getContext('2d');

    // Support device pixel ratio for sharp rendering on retina screens
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.floor(viewport.width * dpr);
    canvas.height = Math.floor(viewport.height * dpr);
    canvas.style.width = Math.floor(viewport.width) + 'px';
    canvas.style.height = Math.floor(viewport.height) + 'px';

    context.setTransform(dpr, 0, 0, dpr, 0, 0);

    const renderContext = {
      canvasContext: context,
      viewport,
    };

    currentRenderTask = page.render(renderContext);
    await currentRenderTask.promise;
    currentRenderTask = null;
  } catch (err) {
    if (err?.name === 'RenderingCancelledException') {
      return;
    }
    console.error('PDF render error:', err);
    loadError.value = true;
  } finally {
    isLoading.value = false;
  }
};

const prevPage = () => {
  if (currentPage.value > 1) {
    currentPage.value--;
    renderPage(currentPage.value);
  }
};

const nextPage = () => {
  if (currentPage.value < totalPages.value) {
    currentPage.value++;
    renderPage(currentPage.value);
  }
};

const zoomIn = () => {
  if (scale.value < 3.0) {
    scale.value = +(scale.value + 0.25).toFixed(2);
    renderPage(currentPage.value);
  }
};

const zoomOut = () => {
  if (scale.value > 0.5) {
    scale.value = +(scale.value - 0.25).toFixed(2);
    renderPage(currentPage.value);
  }
};

watch(
  () => props.streamUrl,
  () => {
    loadPdf();
  }
);

onMounted(() => {
  loadPdf();
});

onUnmounted(() => {
  if (currentRenderTask) {
    currentRenderTask.cancel();
    currentRenderTask = null;
  }
  if (currentLoadingTask) {
    try {
      currentLoadingTask.destroy();
    } catch (e) {}
    currentLoadingTask = null;
  }
  if (pdfDoc.value) {
    try {
      if (typeof pdfDoc.value.cleanup === 'function') {
        pdfDoc.value.cleanup();
      }
    } catch (e) {}
    pdfDoc.value = null;
  }
});
</script>
