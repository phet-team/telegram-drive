<template>
  <Transition name="fade">
    <div
      v-if="isOpen"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4 select-none"
    >
      <div
        class="bg-white rounded-[28px] shadow-[0_8px_32px_rgba(0,0,0,0.18)] max-w-sm w-full p-6 border border-gray-150 animate-in fade-in zoom-in-95 duration-150"
        @click.stop
      >
        <h3 class="text-2xl font-normal text-[#1f1f1f] mb-5 tracking-tight">New folder</h3>
        
        <input
          v-model="folderName"
          type="text"
          placeholder="Folder name"
          class="w-full px-4 py-3 border border-gray-300 rounded-xl focus:outline-none focus:border-[#0b57d0] focus:ring-2 focus:ring-[#0b57d0]/20 text-sm mb-6 transition-all"
          @keyup.enter="handleCreate"
          ref="inputRef"
        />

        <div class="flex justify-end items-center gap-2">
          <button
            type="button"
            class="px-5 py-2 text-sm font-medium text-[#0b57d0] hover:bg-[#edf2fc] rounded-full transition-colors cursor-pointer"
            @click="handleClose"
          >
            Cancel
          </button>
          <button
            type="button"
            class="px-6 py-2 text-sm font-medium text-white bg-[#0b57d0] hover:bg-[#0842a0] rounded-full transition-all shadow-xs disabled:opacity-40 cursor-pointer"
            :disabled="!folderName.trim()"
            @click="handleCreate"
          >
            Create
          </button>
        </div>
      </div>
    </div>
  </Transition>
</template>

<script setup>
import { ref, watch, nextTick } from 'vue';
import { useDriveStore } from '../../stores/drive';

const props = defineProps({
  isOpen: Boolean,
});
const emit = defineEmits(['close']);

const drive = useDriveStore();
const folderName = ref('Untitled folder');
const inputRef = ref(null);

watch(() => props.isOpen, (newVal) => {
  if (newVal) {
    folderName.value = 'Untitled folder';
    nextTick(() => {
      inputRef.value?.focus();
      inputRef.value?.select();
    });
  }
});

const handleClose = () => {
  emit('close');
};

const handleCreate = async () => {
  if (!folderName.value.trim()) return;
  const success = await drive.createFolder(folderName.value.trim());
  if (success) {
    handleClose();
  }
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
