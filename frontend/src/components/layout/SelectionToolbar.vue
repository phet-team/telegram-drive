<template>
  <div class="flex items-center gap-1.5 sm:gap-2 select-none animate-in fade-in duration-150 shrink-0">
    <!-- Count badge + Deselect button -->
    <div class="flex items-center bg-[#c2e7ff]/70 text-[#001d35] pl-1 pr-2 sm:pr-2.5 py-0.5 sm:py-1 rounded-full text-xs font-semibold gap-1 shrink-0">
      <button
        type="button"
        class="p-1 hover:bg-black/10 rounded-full transition-colors cursor-pointer text-[#001d35]"
        title="Clear selection (Esc)"
        @click="drive.clearSelection()"
      >
        <X class="w-3.5 h-3.5" />
      </button>
      <span class="text-xs sm:text-[13px]">{{ drive.selectedItems.length }}</span>
    </div>

    <!-- Quick Batch Action Buttons -->
    <div class="flex items-center gap-0.5 sm:gap-1 shrink-0 bg-[#f0f4f9] px-1 py-0.5 rounded-full border border-gray-200/60">
      <!-- Download (if contains file) -->
      <button
        v-if="hasDownloadableFiles"
        type="button"
        class="p-2 text-[#444746] hover:text-[#1f1f1f] hover:bg-black/5 rounded-full transition-colors cursor-pointer"
        title="Download"
        @click="drive.downloadSelected()"
      >
        <Download class="w-4 h-4 sm:w-4.5 sm:h-4.5" />
      </button>

      <!-- Move to Folder -->
      <button
        v-if="drive.currentSection !== 'trash'"
        type="button"
        class="p-2 text-[#444746] hover:text-[#1f1f1f] hover:bg-black/5 rounded-full transition-colors cursor-pointer"
        title="Move to..."
        @click="emit('openMoveModal')"
      >
        <FolderInput class="w-4 h-4 sm:w-4.5 sm:h-4.5" />
      </button>

      <!-- Star / Unstar -->
      <button
        v-if="drive.currentSection !== 'trash'"
        type="button"
        class="p-2 text-[#444746] hover:text-[#1f1f1f] hover:bg-black/5 rounded-full transition-colors cursor-pointer"
        :title="allStarred ? 'Remove from starred' : 'Add to starred'"
        @click="drive.starSelected()"
      >
        <Star :class="['w-4 h-4 sm:w-4.5 sm:h-4.5', allStarred ? 'fill-[#f4b400] text-[#f4b400]' : '']" />
      </button>

      <!-- Rename (only if single item) -->
      <button
        v-if="drive.selectedItems.length === 1 && drive.currentSection !== 'trash' && drive.currentSection !== 'shared'"
        type="button"
        class="p-2 text-[#444746] hover:text-[#1f1f1f] hover:bg-black/5 rounded-full transition-colors cursor-pointer"
        title="Rename"
        @click="emit('openRenameModal', drive.selectedItems[0])"
      >
        <Edit2 class="w-4 h-4 sm:w-4.5 sm:h-4.5" />
      </button>

      <!-- Share (only if single item) -->
      <button
        v-if="drive.selectedItems.length === 1 && drive.currentSection !== 'trash' && drive.currentSection !== 'shared'"
        type="button"
        class="p-2 text-[#444746] hover:text-[#1f1f1f] hover:bg-black/5 rounded-full transition-colors cursor-pointer"
        title="Share"
        @click="emit('openShareModal', drive.selectedItems[0])"
      >
        <UserPlus class="w-4 h-4 sm:w-4.5 sm:h-4.5" />
      </button>

      <!-- Restore (if in Trash) -->
      <button
        v-if="drive.currentSection === 'trash'"
        type="button"
        class="p-2 text-[#444746] hover:text-[#1f1f1f] hover:bg-black/5 rounded-full transition-colors cursor-pointer"
        title="Restore selected"
        @click="drive.restoreSelected()"
      >
        <RotateCcw class="w-4 h-4 sm:w-4.5 sm:h-4.5" />
      </button>

      <!-- Move to Trash / Delete -->
      <button
        type="button"
        class="p-2 text-[#444746] hover:text-red-600 hover:bg-red-50 rounded-full transition-colors cursor-pointer"
        :title="drive.currentSection === 'trash' ? 'Delete forever' : 'Move to trash'"
        @click="handleTrashOrDelete"
      >
        <Trash2 class="w-4 h-4 sm:w-4.5 sm:h-4.5" />
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue';
import { X, Download, FolderInput, Star, Edit2, UserPlus, Trash2, RotateCcw } from 'lucide-vue-next';
import { useDriveStore } from '../../stores/drive';

const emit = defineEmits(['openMoveModal', 'openRenameModal', 'openShareModal', 'openDeleteConfirmModal']);
const drive = useDriveStore();

const hasDownloadableFiles = computed(() => {
  return drive.selectedItems.some(i => i.type === 'file');
});

const allStarred = computed(() => {
  return drive.selectedItems.length > 0 && drive.selectedItems.every(i => i.is_starred);
});

const handleTrashOrDelete = () => {
  if (drive.currentSection === 'trash') {
    emit('openDeleteConfirmModal');
  } else {
    drive.trashSelected();
  }
};
</script>
