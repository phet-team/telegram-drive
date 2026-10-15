<template>
  <div
    v-if="isDragging"
    class="fixed inset-0 z-50 bg-[#0b57d0]/10 backdrop-blur-xs border-3 border-dashed border-[#0b57d0] m-3 rounded-3xl flex flex-col items-center justify-center pointer-events-none transition-all duration-200 select-none animate-in fade-in zoom-in-95"
  >
    <div class="bg-white/95 px-10 py-8 rounded-3xl shadow-[0_8px_32px_rgba(0,0,0,0.18)] flex flex-col items-center gap-4 border border-[#c2e7ff]">
      <div class="w-16 h-16 rounded-full bg-[#c2e7ff] text-[#0b57d0] flex items-center justify-center animate-bounce shadow-inner">
        <UploadCloud class="w-8 h-8" />
      </div>
      <div class="text-xl font-medium text-[#1f1f1f]">
        Drop files to upload
      </div>
      <div class="text-xs font-medium text-[#747775]">
        Upload directly to <span class="text-[#0b57d0] font-semibold">"{{ folderTitle }}"</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue';
import { UploadCloud } from 'lucide-vue-next';
import { useUploadStore } from '../../stores/upload';
import { useDriveStore } from '../../stores/drive';

const uploadStore = useUploadStore();
const drive = useDriveStore();
const isDragging = ref(false);
let dragCounter = 0;

const folderTitle = computed(() => {
  return drive.currentFolder?.name || 'My Drive';
});

const canUploadHere = computed(() => {
  if (drive.currentSection === 'trash') return false;
  if (drive.currentSection === 'starred') {
    return !!drive.currentFolder && (drive.currentFolder.effective_role === 'editor' || drive.currentFolder.effective_role === 'owner');
  }
  if (drive.currentSection === 'shared') {
    return !!drive.currentFolder && (drive.currentFolder.effective_role === 'editor' || drive.currentFolder.effective_role === 'owner');
  }
  return true;
});

const handleDragEnter = (e) => {
  e.preventDefault();
  if (!canUploadHere.value) return;
  dragCounter++;
  if (e.dataTransfer.types && e.dataTransfer.types.includes('Files')) {
    isDragging.value = true;
  }
};

const handleDragLeave = (e) => {
  e.preventDefault();
  if (!canUploadHere.value) return;
  dragCounter--;
  if (dragCounter <= 0) {
    isDragging.value = false;
    dragCounter = 0;
  }
};

const handleDragOver = (e) => {
  e.preventDefault();
};

const handleDrop = (e) => {
  e.preventDefault();
  isDragging.value = false;
  dragCounter = 0;
  if (!canUploadHere.value) return;

  const files = Array.from(e.dataTransfer.files || []);
  if (files.length > 0) {
    uploadStore.enqueueFiles(files, drive.currentFolder?.id);
  }
};

onMounted(() => {
  window.addEventListener('dragenter', handleDragEnter);
  window.addEventListener('dragleave', handleDragLeave);
  window.addEventListener('dragover', handleDragOver);
  window.addEventListener('drop', handleDrop);
});

onUnmounted(() => {
  window.removeEventListener('dragenter', handleDragEnter);
  window.removeEventListener('dragleave', handleDragLeave);
  window.removeEventListener('dragover', handleDragOver);
  window.removeEventListener('drop', handleDrop);
});
</script>
