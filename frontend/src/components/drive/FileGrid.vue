<template>
  <div class="flex flex-col gap-6 select-none">
    <!-- Folders Section -->
    <div v-if="filteredFolders.length > 0">
      <div class="flex items-center justify-between mb-3 px-1">
        <h3 class="text-sm font-medium text-[#444746]">
          Folders
        </h3>
        <span class="text-xs text-[#747775]">{{ filteredFolders.length }}</span>
      </div>

      <div class="grid grid-cols-1 xs:grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-2.5 sm:gap-3">
        <div
          v-for="folder in filteredFolders"
          :key="folder.id"
          :data-selectable-id="folder.id"
          :draggable="isDesktop"
          :class="[
            'relative flex items-center justify-between px-3.5 py-3 rounded-xl border cursor-pointer transition-all duration-150 group shadow-xs select-none',
            activeDropFolderId === folder.id
              ? 'bg-[#c2e7ff] border-[#0b57d0] ring-2 ring-[#0b57d0] scale-[1.02] shadow-md z-10'
              : drive.isSelected(folder)
                ? 'bg-[#c2e7ff]/40 border-[#0b57d0] ring-1 ring-[#0b57d0]'
                : 'bg-[#f8fafd] hover:bg-[#edf2fc] border-gray-200/80 hover:border-[#c2e7ff]'
          ]"
          @click="handleItemClick(folder, 'folder', $event)"
          @dblclick="handleOpenFolder(folder)"
          @contextmenu.prevent="handleContextMenu($event, { ...folder, type: 'folder' })"
          @dragstart="handleDragStart(folder, 'folder', $event)"
          @dragend="handleDragEnd"
          @dragover="handleFolderDragOver(folder, $event)"
          @dragleave="handleFolderDragLeave(folder, $event)"
          @drop="handleFolderDrop(folder, $event)"
          @touchstart="handleTouchStart(folder, 'folder')"
          @touchend="handleTouchEnd"
          @touchmove="handleTouchMove"
        >
          <div class="flex items-center gap-2.5 truncate min-w-0">
            <FileIcon :is-folder="true" size="sm" class="shrink-0" />
            <div class="truncate">
              <span class="text-sm font-medium text-[#1f1f1f] truncate block">{{ folder.name }}</span>
              <span v-if="drive.searchQuery.trim()" class="text-[10px] text-[#747775] font-normal block truncate">
                In: {{ folder.parent_name || 'My Drive' }}
              </span>
              <span v-else-if="drive.currentSection === 'shared'" class="text-[10px] text-[#0b57d0] font-medium block truncate">
                {{ formatUserDisplay(folder, auth.user).name }}
              </span>
            </div>
          </div>

          <div class="flex items-center gap-1 shrink-0">
            <Star v-if="folder.is_starred" class="w-3.5 h-3.5 fill-[#f4b400] text-[#f4b400]" />
            <button
              type="button"
              class="opacity-100 lg:opacity-0 lg:group-hover:opacity-100 p-1.5 sm:p-1 text-[#444746] hover:text-[#1f1f1f] hover:bg-black/5 rounded-full transition-all cursor-pointer"
              title="More actions"
              @click.stop="handleContextMenu($event, { ...folder, type: 'folder' })"
            >
              <MoreVertical class="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Files Section -->
    <div v-if="filteredFiles.length > 0">
      <div class="flex items-center justify-between mb-3 px-1">
        <h3 class="text-sm font-medium text-[#444746]">
          Files
        </h3>
        <span class="text-xs text-[#747775]">{{ filteredFiles.length }}</span>
      </div>

      <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3 sm:gap-4">
        <div
          v-for="file in filteredFiles"
          :key="file.id"
          :data-selectable-id="file.id"
          :draggable="isDesktop"
          :class="[
            'relative flex flex-col bg-white rounded-2xl border overflow-hidden cursor-pointer transition-all duration-200 group select-none',
            drive.isSelected(file)
              ? 'bg-[#c2e7ff]/30 border-[#0b57d0] ring-2 ring-[#0b57d0] shadow-md'
              : 'border-gray-200/80 hover:border-[#c2e7ff] hover:shadow-[0_1px_3px_0_rgba(60,64,67,0.3),0_4px_8px_3px_rgba(60,64,67,0.15)]'
          ]"
          @click="handleItemClick(file, 'file', $event)"
          @dblclick="handleOpenFile(file)"
          @contextmenu.prevent="handleContextMenu($event, { ...file, type: 'file' })"
          @dragstart="handleDragStart(file, 'file', $event)"
          @dragend="handleDragEnd"
          @touchstart="handleTouchStart(file, 'file')"
          @touchend="handleTouchEnd"
          @touchmove="handleTouchMove"
        >
          <!-- Thumbnail / Preview Canvas Area -->
          <div class="h-28 sm:h-36 bg-[#f0f4f9] group-hover:bg-[#e9eef6] flex items-center justify-center p-4 sm:p-6 border-b border-gray-100 transition-colors relative">
            <FileIcon :mime-type="file.mime_type" size="xl" />

            <Star v-if="file.is_starred" class="w-4 h-4 fill-[#f4b400] text-[#f4b400] absolute top-2.5 right-2.5 drop-shadow-xs" />
          </div>

          <!-- Bottom Card Meta Info -->
          <div class="p-2.5 sm:p-3.5 flex items-center justify-between gap-1.5 sm:gap-2">
            <div class="flex items-center gap-2 truncate flex-1 min-w-0">
              <FileIcon :mime-type="file.mime_type" size="sm" class="shrink-0" />
              <div class="truncate">
                <div class="text-[12.5px] sm:text-[13px] font-medium text-[#1f1f1f] truncate" :title="file.name">
                  {{ file.name }}
                </div>
                <div class="text-[10.5px] sm:text-[11px] text-[#747775] mt-0.5 flex items-center gap-1.5 truncate">
                  <span v-if="drive.searchQuery.trim()" class="text-[#444746] font-medium truncate">
                    In: {{ file.folder_name || 'My Drive' }}
                  </span>
                  <span v-if="drive.searchQuery.trim()">•</span>
                  <span>{{ formatBytes(file.size) }}</span>
                  <template v-if="drive.currentSection === 'shared'">
                    <span>•</span>
                    <span class="truncate text-[#0b57d0] font-medium">{{ formatUserDisplay(file, auth.user).name }}</span>
                  </template>
                </div>
              </div>
            </div>

            <button
              type="button"
              class="opacity-100 lg:opacity-0 lg:group-hover:opacity-100 p-1.5 sm:p-1 text-[#444746] hover:text-[#1f1f1f] hover:bg-black/5 rounded-full transition-all shrink-0 cursor-pointer"
              title="More actions"
              @click.stop="handleContextMenu($event, { ...file, type: 'file' })"
            >
              <MoreVertical class="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Empty State -->
    <div
      v-if="filteredFolders.length === 0 && filteredFiles.length === 0 && !drive.loading"
      class="flex flex-col items-center justify-center py-24 text-center select-none"
    >
      <div class="w-40 h-40 mb-4 flex items-center justify-center">
        <svg viewBox="0 0 160 160" width="140" height="140" fill="none" xmlns="http://www.w3.org/2000/svg">
          <rect x="20" y="45" width="120" height="90" rx="16" fill="#F0F4F9" stroke="#E0E3E7" stroke-width="2"/>
          <path d="M20 60C20 51.7157 26.7157 45 35 45H65L75 57H125C133.284 57 140 63.7157 140 72V119C140 127.284 133.284 134 125 134H35C26.7157 134 20 127.284 20 119V60Z" fill="#E9EEF6"/>
          <circle cx="80" cy="95" r="22" fill="#D3E3FD"/>
          <path d="M80 85V105M70 95H90" stroke="#0B57D0" stroke-width="3" stroke-linecap="round"/>
        </svg>
      </div>
      <p class="text-lg font-medium text-[#1f1f1f]">{{ emptyTitle }}</p>
      <p class="text-sm text-[#747775] mt-1 max-w-sm">
        {{ emptySubtitle }}
      </p>
      <button
        v-if="drive.searchQuery.trim()"
        type="button"
        class="mt-4 px-4 py-2 bg-[#0b57d0] text-white hover:bg-[#0842a0] rounded-full text-xs font-medium transition-colors cursor-pointer"
        @click="drive.clearSearch()"
      >
        Clear search
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue';
import { MoreVertical, Star } from 'lucide-vue-next';
import { useDriveStore } from '../../stores/drive';
import { useAuthStore } from '../../stores/auth';
import { useFeedbackStore } from '../../stores/feedback';
import { formatUserDisplay } from '../../utils/user';
import FileIcon from './FileIcon.vue';

const emit = defineEmits(['openFolder', 'openFile', 'contextMenu']);
const drive = useDriveStore();
const auth = useAuthStore();
const feedback = useFeedbackStore();

const activeDropFolderId = ref(null);
const isDesktop = computed(() => typeof window !== 'undefined' && window.innerWidth >= 768);

const allDisplayItems = computed(() => [
  ...filteredFolders.value.map(f => ({ ...f, type: 'folder' })),
  ...filteredFiles.value.map(f => ({ ...f, type: 'file' })),
]);

let touchTimer = null;
let touchMoved = false;
let justLongPressed = false;

const handleTouchStart = (item, type) => {
  touchMoved = false;
  justLongPressed = false;
  if (touchTimer) clearTimeout(touchTimer);
  touchTimer = setTimeout(() => {
    if (!touchMoved) {
      justLongPressed = true;
      if (navigator.vibrate) navigator.vibrate(40);
      drive.selectItem({ ...item, type }, { isToggle: true });
    }
  }, 400);
};

const handleTouchMove = () => {
  touchMoved = true;
  if (touchTimer) clearTimeout(touchTimer);
};

const handleTouchEnd = () => {
  if (touchTimer) clearTimeout(touchTimer);
};

const handleOpenFolder = (folder) => {
  emit('openFolder', folder);
};

const handleOpenFile = (file) => {
  emit('openFile', file);
};

const handleItemClick = (item, type, e) => {
  if (justLongPressed) {
    justLongPressed = false;
    return;
  }

  const typedItem = { ...item, type };

  // Mobile (< 768px):
  if (window.innerWidth < 768) {
    if (drive.selectedItems.length > 0) {
      drive.selectItem(typedItem, { isToggle: true });
    } else {
      if (type === 'folder') handleOpenFolder(item);
      else handleOpenFile(item);
    }
    return;
  }

  // Desktop: Single click ONLY focuses/selects
  if (e.ctrlKey || e.metaKey) {
    drive.selectItem(typedItem, { isToggle: true });
  } else if (e.shiftKey) {
    drive.selectItem(typedItem, { isRange: true, allItems: allDisplayItems.value });
  } else {
    drive.selectItem(typedItem);
  }
};

const handleDragStart = (item, type, e) => {
  const typedItem = { ...item, type };
  let itemsToDrag = [];
  if (drive.isSelected(typedItem)) {
    itemsToDrag = [...drive.selectedItems];
  } else {
    drive.selectItem(typedItem);
    itemsToDrag = [typedItem];
  }
  drive.draggedItems = itemsToDrag;

  e.dataTransfer.effectAllowed = 'move';
  e.dataTransfer.setData('text/plain', JSON.stringify(itemsToDrag.map(i => i.id)));

  if (e.dataTransfer.setDragImage && itemsToDrag.length > 1) {
    const ghost = document.createElement('div');
    ghost.className = 'fixed -top-96 -left-96 bg-[#0b57d0] text-white px-3 py-1.5 rounded-full text-xs font-semibold shadow-lg z-50 pointer-events-none flex items-center gap-1.5';
    ghost.textContent = `Moving ${itemsToDrag.length} items`;
    document.body.appendChild(ghost);
    e.dataTransfer.setDragImage(ghost, 15, 15);
    setTimeout(() => {
      if (document.body.contains(ghost)) document.body.removeChild(ghost);
    }, 100);
  }
};

const handleDragEnd = () => {
  drive.draggedItems = [];
  activeDropFolderId.value = null;
};

const handleFolderDragOver = (folder, e) => {
  if (drive.draggedItems.length === 0) return;
  // Cannot drop into itself or one of the dragged folders
  const hasSelf = drive.draggedItems.some(i => i.type === 'folder' && i.id === folder.id);
  if (hasSelf) return;

  e.preventDefault();
  e.dataTransfer.dropEffect = 'move';
  activeDropFolderId.value = folder.id;
};

const handleFolderDragLeave = (folder, e) => {
  if (!e.currentTarget.contains(e.relatedTarget)) {
    if (activeDropFolderId.value === folder.id) {
      activeDropFolderId.value = null;
    }
  }
};

const handleFolderDrop = async (folder, e) => {
  e.preventDefault();
  activeDropFolderId.value = null;
  if (drive.draggedItems.length === 0) return;
  const hasSelf = drive.draggedItems.some(i => i.type === 'folder' && i.id === folder.id);
  if (hasSelf) return;

  const count = drive.draggedItems.length;
  const success = await drive.moveSelected(folder.id, drive.draggedItems);
  if (success) {
    feedback.showToast('info', `Moved ${count} item${count > 1 ? 's' : ''} to "${folder.name}"`);
  }
};

const emptyTitle = computed(() => {
  if (drive.searchQuery.trim()) return `No results found for "${drive.searchQuery}"`;
  if (drive.currentSection === 'shared') return 'No shared files';
  if (drive.currentSection === 'starred') return 'No starred files';
  if (drive.currentSection === 'trash') return 'Trash is empty';
  return 'A place for all your files';
});

const emptySubtitle = computed(() => {
  if (drive.searchQuery.trim()) return 'Check your spelling or try different keywords';
  if (drive.currentSection === 'shared') return 'Items shared with you by others will appear here';
  if (drive.currentSection === 'starred') return 'Add stars to things that you want to easily find later';
  if (drive.currentSection === 'trash') return 'Items moved to trash will appear here';
  return 'Drag and drop files here, or use the New button to upload';
});

const matchesTypeFilter = (file) => {
  if (drive.selectedTypeFilter === 'all') return true;
  const mt = (file.mime_type || '').toLowerCase();
  switch (drive.selectedTypeFilter) {
    case 'pdf':
      return mt === 'application/pdf';
    case 'doc':
      return mt.includes('document') || mt.includes('word') || mt.includes('text/plain');
    case 'sheet':
      return mt.includes('sheet') || mt.includes('excel') || mt === 'text/csv';
    case 'image':
      return mt.startsWith('image/');
    case 'video':
      return mt.startsWith('video/');
    case 'archive':
      return mt.includes('zip') || mt.includes('tar') || mt.includes('gzip') || mt.includes('compressed');
    default:
      return true;
  }
};

const filteredFolders = computed(() => {
  if (drive.selectedTypeFilter !== 'all') return [];
  let list = drive.folders;
  if (drive.currentSection === 'starred') {
    list = list.filter(f => f.is_starred);
  }
  return list;
});

const filteredFiles = computed(() => {
  let list = drive.files.filter(matchesTypeFilter);
  if (drive.currentSection === 'starred') {
    list = list.filter(f => f.is_starred);
  }
  return list;
});

const handleContextMenu = (event, item) => {
  emit('contextMenu', { event, item });
};

const formatBytes = (bytes) => {
  if (!bytes) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
};
</script>
