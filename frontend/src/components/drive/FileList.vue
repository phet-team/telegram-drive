<template>
  <div class="bg-white rounded-2xl border border-gray-200/80 overflow-hidden shadow-xs select-none">
    <div class="overflow-x-auto w-full">
      <table class="w-full text-left text-sm text-[#1f1f1f]">
        <thead class="bg-[#f8fafd] text-[12px] font-semibold text-[#444746] tracking-wider border-b border-gray-200">
          <tr>
            <th scope="col" class="py-3 px-3 sm:px-4 font-medium">Name</th>
            <th v-if="drive.searchQuery.trim()" scope="col" class="py-3 px-4 hidden md:table-cell font-medium">Location</th>
            <th v-else scope="col" class="py-3 px-4 hidden md:table-cell font-medium">Owner</th>
            <th scope="col" class="py-3 px-4 hidden sm:table-cell font-medium">Last modified</th>
            <th scope="col" class="py-3 px-4 hidden sm:table-cell font-medium">File size</th>
            <th scope="col" class="py-3 px-2 text-right"></th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-100">
          <!-- Folders -->
          <tr
            v-for="folder in filteredFolders"
            :key="folder.id"
            :data-selectable-id="folder.id"
            :draggable="isDesktop"
            :class="[
              'transition-colors cursor-pointer group select-none',
              activeDropFolderId === folder.id
                ? 'bg-[#c2e7ff] text-[#0b57d0] ring-2 ring-inset ring-[#0b57d0]'
                : drive.isSelected(folder)
                  ? 'bg-[#c2e7ff]/40 hover:bg-[#c2e7ff]/60 text-[#001d35]'
                  : 'hover:bg-[#f0f4f9]'
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
            <td class="py-2.5 px-3 sm:px-4 flex items-center gap-2 sm:gap-2.5 truncate max-w-xs">
              <FileIcon :is-folder="true" size="sm" class="shrink-0" />
              <div class="truncate">
                <span class="font-medium text-[#1f1f1f] truncate text-[13.5px] block">{{ folder.name }}</span>
                <div v-if="drive.searchQuery.trim()" class="sm:hidden text-[11px] text-[#747775] font-normal mt-0.5">
                  In: {{ folder.parent_name || 'My Drive' }}
                </div>
                <div v-else-if="drive.currentSection === 'shared'" class="sm:hidden text-[11px] text-[#0b57d0] font-medium mt-0.5">
                  {{ formatUserDisplay(folder, auth.user).name }}
                </div>
              </div>
              <Star v-if="folder.is_starred" class="w-3.5 h-3.5 fill-[#f4b400] text-[#f4b400] shrink-0 ml-auto sm:ml-0" />
            </td>
            <td v-if="drive.searchQuery.trim()" class="py-2.5 px-4 text-xs text-[#444746] hidden md:table-cell truncate">
              📁 In: {{ folder.parent_name || 'My Drive' }}
            </td>
            <td v-else class="py-2.5 px-4 text-xs text-[#747775] hidden md:table-cell truncate">
              <div class="flex items-center gap-1.5 truncate">
                <img
                  v-if="formatUserDisplay(folder, auth.user).avatar"
                  :src="formatUserDisplay(folder, auth.user).avatar"
                  class="w-4 h-4 rounded-full object-cover shrink-0 border border-gray-200"
                />
                <span class="truncate">
                  {{ formatUserDisplay(folder, auth.user).isMe ? 'me' : formatUserDisplay(folder, auth.user).name }}
                </span>
              </div>
            </td>
            <td class="py-2.5 px-4 text-xs text-[#747775] hidden sm:table-cell">
              {{ formatDate(folder.updated_at) }}
            </td>
            <td class="py-2.5 px-4 text-xs text-[#747775] hidden sm:table-cell">—</td>
            <td class="py-2.5 px-2 text-right">
              <button
                type="button"
                class="opacity-100 lg:opacity-0 lg:group-hover:opacity-100 p-1.5 sm:p-1 text-[#444746] hover:text-[#1f1f1f] hover:bg-black/5 rounded-full transition-all mr-1 sm:mr-2 cursor-pointer"
                title="More actions"
                @click.stop="handleContextMenu($event, { ...folder, type: 'folder' })"
              >
                <MoreVertical class="w-4 h-4" />
              </button>
            </td>
          </tr>

          <!-- Files -->
          <tr
            v-for="file in filteredFiles"
            :key="file.id"
            :data-selectable-id="file.id"
            :draggable="isDesktop"
            :class="[
              'transition-colors cursor-pointer group select-none',
              drive.isSelected(file)
                ? 'bg-[#c2e7ff]/40 hover:bg-[#c2e7ff]/60 text-[#001d35]'
                : 'hover:bg-[#f0f4f9]'
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
            <td class="py-2.5 px-3 sm:px-4 flex items-center gap-2 sm:gap-2.5 truncate max-w-xs">
              <FileIcon :mime-type="file.mime_type" size="sm" class="shrink-0" />
              <div class="truncate">
                <span class="font-medium text-[#1f1f1f] truncate text-[13.5px] block">{{ file.name }}</span>
                <div class="sm:hidden text-[11px] text-[#747775] flex items-center gap-1.5 mt-0.5">
                  <span v-if="drive.searchQuery.trim()" class="text-[#444746] font-medium">
                    In: {{ file.folder_name || 'My Drive' }}
                  </span>
                  <span v-if="drive.searchQuery.trim()">•</span>
                  <span>{{ formatBytes(file.size) }}</span>
                  <template v-if="drive.currentSection === 'shared' && !drive.searchQuery.trim()">
                    <span>•</span>
                    <span class="text-[#0b57d0] font-medium">{{ formatUserDisplay(file, auth.user).name }}</span>
                  </template>
                </div>
              </div>
              <Star v-if="file.is_starred" class="w-3.5 h-3.5 fill-[#f4b400] text-[#f4b400] shrink-0 ml-auto sm:ml-0" />
            </td>
            <td v-if="drive.searchQuery.trim()" class="py-2.5 px-4 text-xs text-[#444746] hidden md:table-cell truncate">
              📁 In: {{ file.folder_name || 'My Drive' }}
            </td>
            <td v-else class="py-2.5 px-4 text-xs text-[#747775] hidden md:table-cell truncate">
              <div class="flex items-center gap-1.5 truncate">
                <img
                  v-if="formatUserDisplay(file, auth.user).avatar"
                  :src="formatUserDisplay(file, auth.user).avatar"
                  class="w-4 h-4 rounded-full object-cover shrink-0 border border-gray-200"
                />
                <span class="truncate">
                  {{ formatUserDisplay(file, auth.user).isMe ? 'me' : formatUserDisplay(file, auth.user).name }}
                </span>
              </div>
            </td>
            <td class="py-2.5 px-4 text-xs text-[#747775] hidden sm:table-cell">
              {{ formatDate(file.updated_at) }}
            </td>
            <td class="py-2.5 px-4 text-xs text-[#747775] font-mono hidden sm:table-cell">
              {{ formatBytes(file.size) }}
            </td>
            <td class="py-2.5 px-2 text-right">
              <button
                type="button"
                class="opacity-100 lg:opacity-0 lg:group-hover:opacity-100 p-1.5 sm:p-1 text-[#444746] hover:text-[#1f1f1f] hover:bg-black/5 rounded-full transition-all mr-1 sm:mr-2 cursor-pointer"
                title="More actions"
                @click.stop="handleContextMenu($event, { ...file, type: 'file' })"
              >
                <MoreVertical class="w-4 h-4" />
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Empty State -->
    <div
      v-if="filteredFolders.length === 0 && filteredFiles.length === 0 && !drive.loading"
      class="py-20 text-center text-[#747775]"
    >
      <p class="text-base font-medium text-[#1f1f1f]">{{ emptyTitle }}</p>
      <p class="text-xs text-[#747775] mt-1">{{ emptySubtitle }}</p>
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

const handleOpenFolder = (folder) => emit('openFolder', folder);
const handleOpenFile = (file) => emit('openFile', file);

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
  return 'No items found';
});

const emptySubtitle = computed(() => {
  if (drive.searchQuery.trim()) return 'Check your spelling or try different keywords';
  return 'This folder has no files or folders matching your criteria';
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
  if (drive.currentSection === 'starred') list = list.filter(f => f.is_starred);
  return list;
});

const filteredFiles = computed(() => {
  let list = drive.files.filter(matchesTypeFilter);
  if (drive.currentSection === 'starred') list = list.filter(f => f.is_starred);
  return list;
});

const handleContextMenu = (event, item) => emit('contextMenu', { event, item });

const formatDate = (dateStr) => {
  if (!dateStr) return '—';
  return new Date(dateStr).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
};

const formatBytes = (bytes) => {
  if (!bytes) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
};
</script>
