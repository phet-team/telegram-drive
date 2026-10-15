<template>
  <div
    v-if="uploadStore.conflictQueue.length > 0"
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs select-none animate-in fade-in duration-200"
  >
    <div
      class="bg-white rounded-3xl w-full max-w-md mx-4 shadow-2xl border border-gray-150 overflow-hidden flex flex-col p-6 animate-in zoom-in-95 duration-200"
    >
      <!-- Header -->
      <div class="flex items-center gap-3.5 mb-4">
        <div class="w-10 h-10 rounded-full bg-blue-50 text-[#0b57d0] flex items-center justify-center shrink-0">
          <Copy class="w-5 h-5" />
        </div>
        <div class="min-w-0 flex-1">
          <h3 class="text-base font-semibold text-[#1f1f1f] truncate">
            File already exists
          </h3>
          <p class="text-xs text-[#747775] truncate" :title="currentConflict?.file?.name">
            "{{ currentConflict?.file?.name }}"
          </p>
        </div>
      </div>

      <p class="text-xs text-[#444746] mb-4">
        An item with this name already exists in this folder. What would you like to do?
      </p>

      <!-- Comparison Card -->
      <div class="bg-[#f8fafd] rounded-2xl p-4 border border-gray-150 flex flex-col gap-2.5 mb-5 text-xs">
        <div class="flex items-center justify-between">
          <span class="text-[#747775]">Existing file:</span>
          <span class="font-medium text-[#1f1f1f]">{{ formatBytes(currentConflict?.existingFile?.size) }}</span>
        </div>
        <div class="h-px bg-gray-200"></div>
        <div class="flex items-center justify-between">
          <span class="text-[#747775]">New file:</span>
          <span class="font-medium text-[#0b57d0]">{{ formatBytes(currentConflict?.file?.size) }}</span>
        </div>
      </div>

      <!-- Multiple Conflicts Checkbox -->
      <div v-if="uploadStore.conflictQueue.length > 1" class="flex items-center gap-2 mb-5 text-xs text-[#444746]">
        <input
          type="checkbox"
          id="applyAll"
          v-model="applyToAll"
          class="rounded text-[#0b57d0] focus:ring-[#0b57d0] cursor-pointer"
        />
        <label for="applyAll" class="cursor-pointer">
          Apply to remaining {{ uploadStore.conflictQueue.length - 1 }} conflicting files
        </label>
      </div>

      <!-- Action Buttons -->
      <div class="flex flex-col sm:flex-row gap-2 justify-end">
        <button
          type="button"
          class="px-4 py-2 rounded-full border border-gray-300 text-xs font-medium text-[#444746] hover:bg-gray-100 transition-colors cursor-pointer"
          @click="resolveAction('skip')"
        >
          Cancel
        </button>
        <button
          type="button"
          class="px-4 py-2 rounded-full border border-blue-200 text-xs font-medium text-[#0b57d0] hover:bg-blue-50 transition-colors cursor-pointer"
          @click="resolveAction('keepBoth')"
        >
          Keep both
        </button>
        <button
          type="button"
          class="px-4 py-2 rounded-full bg-[#0b57d0] hover:bg-[#0842a0] text-xs font-medium text-white transition-colors shadow-sm cursor-pointer"
          @click="resolveAction('replace')"
        >
          Replace existing
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue';
import { Copy } from 'lucide-vue-next';
import { useUploadStore } from '../../stores/upload';

const uploadStore = useUploadStore();
const applyToAll = ref(false);

const currentConflict = computed(() => {
  return uploadStore.conflictQueue[0] || null;
});

const resolveAction = (action) => {
  uploadStore.resolveConflict(action, applyToAll.value);
  applyToAll.value = false;
};

const formatBytes = (bytes) => {
  if (!bytes) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
};
</script>
