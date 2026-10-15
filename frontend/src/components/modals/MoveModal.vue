<template>
  <Transition name="fade">
    <div
      v-if="isOpen"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4 select-none"
    >
      <div
        class="bg-white rounded-3xl shadow-2xl border border-gray-150 w-full max-w-md overflow-hidden flex flex-col max-h-[85vh] animate-in fade-in zoom-in-95 duration-150"
      >
        <!-- Modal Header -->
        <div class="px-6 pt-5 pb-3 border-b border-gray-100 flex items-center justify-between">
          <div class="flex items-center gap-2.5">
            <FolderInput class="w-5 h-5 text-[#0b57d0]" />
            <h3 class="text-base font-medium text-[#1f1f1f]">
              {{ titleText }}
            </h3>
          </div>
          <button
            type="button"
            class="text-gray-400 hover:text-gray-600 p-1 rounded-full hover:bg-black/5 transition-colors cursor-pointer"
            @click="emit('close')"
          >
            <X class="w-5 h-5" />
          </button>
        </div>

        <!-- Breadcrumbs Navigation inside Modal -->
        <div class="px-6 py-2.5 bg-[#f8fafd] border-b border-gray-100 flex items-center gap-1.5 text-xs text-[#444746] overflow-x-auto">
          <button
            type="button"
            :class="['hover:text-[#0b57d0] hover:underline cursor-pointer font-medium', currentTargetId === null ? 'text-[#0b57d0] font-semibold' : '']"
            @click="navigateFolder(null)"
          >
            My Drive
          </button>
          <template v-for="crumb in navTrail" :key="crumb.id">
            <ChevronRight class="w-3.5 h-3.5 text-gray-400 shrink-0" />
            <button
              type="button"
              :class="['hover:text-[#0b57d0] hover:underline cursor-pointer truncate max-w-[120px]', currentTargetId === crumb.id ? 'text-[#0b57d0] font-semibold' : '']"
              @click="navigateFolder(crumb.id)"
            >
              {{ crumb.name }}
            </button>
          </template>
        </div>

        <!-- Folder List -->
        <div class="flex-1 overflow-y-auto p-3 min-h-[220px]">
          <div v-if="isLoading" class="flex items-center justify-center py-16">
            <div class="animate-spin rounded-full h-7 w-7 border-2 border-[#0b57d0] border-t-transparent"></div>
          </div>

          <div v-else-if="availableFolders.length === 0" class="py-12 text-center text-xs text-[#747775]">
            <Folder class="w-8 h-8 text-gray-300 mx-auto mb-2" />
            No subfolders here
          </div>

          <div v-else class="flex flex-col gap-1">
            <div
              v-for="folder in availableFolders"
              :key="folder.id"
              :class="[
                'flex items-center justify-between px-3.5 py-2.5 rounded-xl transition-colors cursor-pointer',
                isFolderDisabled(folder)
                  ? 'opacity-40 cursor-not-allowed bg-gray-50'
                  : 'hover:bg-[#f0f4f9] text-[#1f1f1f]'
              ]"
              @click="!isFolderDisabled(folder) && navigateFolder(folder.id, folder.name)"
            >
              <div class="flex items-center gap-3 truncate min-w-0">
                <Folder class="w-4.5 h-4.5 text-[#0b57d0] fill-[#c2e7ff] shrink-0" />
                <span class="text-sm font-medium truncate">{{ folder.name }}</span>
              </div>
              <ChevronRight class="w-4 h-4 text-gray-400 shrink-0" />
            </div>
          </div>
        </div>

        <!-- Modal Footer Actions -->
        <div class="px-6 py-4 bg-[#f8fafd] border-t border-gray-100 flex items-center justify-between gap-3">
          <button
            type="button"
            class="px-4 py-2 text-xs font-medium text-[#444746] hover:text-[#1f1f1f] hover:bg-black/5 rounded-full transition-colors cursor-pointer"
            @click="emit('close')"
          >
            Cancel
          </button>

          <button
            type="button"
            :disabled="isSubmitting || isCurrentFolderTarget"
            :class="[
              'px-5 py-2 rounded-full text-xs font-medium transition-all flex items-center gap-2 cursor-pointer shadow-xs',
              isCurrentFolderTarget || isSubmitting
                ? 'bg-gray-200 text-gray-400 cursor-not-allowed shadow-none'
                : 'bg-[#0b57d0] hover:bg-[#0842a0] text-white'
            ]"
            @click="handleConfirmMove"
          >
            <div v-if="isSubmitting" class="animate-spin rounded-full h-3.5 w-3.5 border-2 border-white border-t-transparent"></div>
            <span>Move here</span>
          </button>
        </div>
      </div>
    </div>
  </Transition>
</template>

<script setup>
import { ref, computed, watch } from 'vue';
import { X, FolderInput, Folder, ChevronRight } from 'lucide-vue-next';
import api from '../../services/api';
import { useDriveStore } from '../../stores/drive';

const props = defineProps({
  isOpen: Boolean,
  targetItems: {
    type: Array,
    default: () => [],
  },
});

const emit = defineEmits(['close', 'moved']);
const drive = useDriveStore();

const currentTargetId = ref(null);
const navTrail = ref([]);
const availableFolders = ref([]);
const isLoading = ref(false);
const isSubmitting = ref(false);

const titleText = computed(() => {
  const count = props.targetItems.length || drive.selectedItems.length;
  if (count <= 1) {
    const item = props.targetItems[0] || drive.selectedItems[0];
    return item ? `Move "${item.name}"` : 'Move item';
  }
  return `Move ${count} items`;
});

// Check if destination is already where the item currently is
const isCurrentFolderTarget = computed(() => {
  const items = props.targetItems.length > 0 ? props.targetItems : drive.selectedItems;
  if (items.length === 1) {
    const it = items[0];
    const parentId = it.type === 'folder' ? it.parent : it.folder;
    return (parentId ?? null) === (currentTargetId.value ?? null);
  }
  return false;
});

// Prevent moving a folder into itself or its own descendants
const isFolderDisabled = (folder) => {
  const items = props.targetItems.length > 0 ? props.targetItems : drive.selectedItems;
  return items.some(it => it.type === 'folder' && it.id === folder.id);
};

const fetchFolderList = async (folderId = null) => {
  isLoading.value = true;
  try {
    const params = { trashed: false };
    if (folderId) {
      params.parent = folderId;
    }
    const { data } = await api.get('/drive/folders/', { params });
    availableFolders.value = data;
  } catch (err) {
    availableFolders.value = [];
  } finally {
    isLoading.value = false;
  }
};

const navigateFolder = (folderId, folderName = '') => {
  currentTargetId.value = folderId;
  if (folderId === null) {
    navTrail.value = [];
  } else {
    const existingIdx = navTrail.value.findIndex(c => c.id === folderId);
    if (existingIdx !== -1) {
      navTrail.value = navTrail.value.slice(0, existingIdx + 1);
    } else {
      navTrail.value.push({ id: folderId, name: folderName });
    }
  }
  fetchFolderList(folderId);
};

watch(
  () => props.isOpen,
  (open) => {
    if (open) {
      currentTargetId.value = null;
      navTrail.value = [];
      fetchFolderList(null);
    }
  }
);

const handleConfirmMove = async () => {
  isSubmitting.value = true;
  try {
    const targetId = currentTargetId.value;
    if (props.targetItems.length > 0) {
      for (const item of props.targetItems) {
        await drive.moveItem(item, targetId);
      }
    } else {
      await drive.moveSelected(targetId);
    }
    emit('moved');
    emit('close');
  } finally {
    isSubmitting.value = false;
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
