<template>
  <div class="h-screen h-[100dvh] w-full max-w-[100vw] flex flex-col bg-drive-bg overflow-hidden text-[#1f1f1f] font-sans" @click="closeContextMenu">
    <!-- Navbar -->
    <Navbar @toggle-sidebar="isMobileSidebarOpen = !isMobileSidebarOpen" />

    <!-- Main Container: Sidebar + Drive Content Canvas -->
    <div class="flex-1 min-h-0 flex overflow-hidden relative">
      <!-- Sidebar (Desktop static / Mobile slide-out drawer) -->
      <Sidebar
        :is-open="isMobileSidebarOpen"
        @close="isMobileSidebarOpen = false"
        @open-create-folder="isCreateFolderModalOpen = true"
      />

      <!-- Main White Content Card -->
      <main class="flex-1 min-h-0 flex flex-col bg-white rounded-none sm:rounded-3xl shadow-[0_1px_3px_0_rgba(60,64,67,0.15)] border-0 sm:border border-gray-200/80 mr-0 mb-0 sm:mr-4 sm:mb-4 overflow-hidden">
        <!-- Top Toolbar & Breadcrumbs Bar -->
        <div class="px-3 sm:px-6 pt-3 sm:pt-4 pb-2.5 sm:pb-3 flex flex-col gap-2.5 sm:gap-3 shrink-0 border-b border-gray-100">
          <div class="flex items-center justify-between min-h-[38px] gap-2">
            <!-- Breadcrumbs is ALWAYS visible on the left -->
            <div class="flex-1 min-w-0">
              <Breadcrumbs @action="handleContextAction" />
            </div>

            <!-- Right Controls: Selection Toolbar when items focused + View Switcher -->
            <div class="flex items-center gap-1.5 sm:gap-2 shrink-0">
              <SelectionToolbar
                v-if="drive.selectedItems.length > 0"
                @open-move-modal="handleOpenBatchMove"
                @open-rename-modal="handleOpenRename"
                @open-share-modal="handleOpenShare"
                @open-delete-confirm-modal="handleOpenBatchDeleteConfirm"
              />

              <!-- View Switcher (Grid / List) -->
              <div class="flex items-center bg-[#f0f4f9] p-1 rounded-full border border-gray-200/60 shrink-0">
                <button
                  type="button"
                  :class="[
                    'p-1.5 rounded-full transition-all cursor-pointer',
                    drive.viewMode === 'list' ? 'bg-white shadow-xs text-[#0b57d0]' : 'text-[#444746] hover:text-[#1f1f1f]'
                  ]"
                  title="List view"
                  @click="drive.viewMode = 'list'"
                >
                  <List class="w-4 h-4" />
                </button>
                <button
                  type="button"
                  :class="[
                    'p-1.5 rounded-full transition-all cursor-pointer',
                    drive.viewMode === 'grid' ? 'bg-white shadow-xs text-[#0b57d0]' : 'text-[#444746] hover:text-[#1f1f1f]'
                  ]"
                  title="Grid view"
                  @click="drive.viewMode = 'grid'"
                >
                  <LayoutGrid class="w-4 h-4" />
                </button>
              </div>
            </div>
          </div>

          <!-- Google Drive Filter Chips -->
          <div class="flex items-center gap-2 overflow-x-auto pb-1 text-xs select-none">
            <button
              v-for="chip in filterChips"
              :key="chip.id"
              type="button"
              :class="[
                'px-3.5 py-1.5 rounded-lg font-medium transition-all cursor-pointer shrink-0 flex items-center gap-1.5',
                drive.selectedTypeFilter === chip.id
                  ? 'bg-[#c2e7ff] text-[#001d35] font-semibold'
                  : 'bg-white border border-gray-300 text-[#444746] hover:bg-[#f0f4f9]'
              ]"
              @click="drive.selectedTypeFilter = chip.id"
            >
              <span>{{ chip.label }}</span>
            </button>
          </div>
        </div>

        <!-- Files and Folders Scrollable Container with Marquee Selection -->
        <div
          ref="scrollContainerRef"
          class="flex-1 min-h-0 overflow-y-auto p-3 sm:p-6 pb-28 sm:pb-36 overscroll-contain relative"
        >
          <!-- Marquee Selection Box Overlay -->
          <div
            v-if="selectionBox"
            class="absolute pointer-events-none border border-[#0b57d0] bg-[#c2e7ff]/30 z-30 rounded shadow-xs"
            :style="{
              left: selectionBox.left + 'px',
              top: selectionBox.top + 'px',
              width: selectionBox.width + 'px',
              height: selectionBox.height + 'px'
            }"
          ></div>

          <div v-if="drive.loading" class="flex flex-col items-center justify-center py-24 gap-3">
            <div class="animate-spin rounded-full h-8 w-8 border-2 border-[#0b57d0] border-t-transparent"></div>
            <span class="text-xs font-medium text-[#747775]">Loading your files...</span>
          </div>

          <template v-else>
            <FileGrid
              v-if="drive.viewMode === 'grid'"
              @open-folder="handleOpenFolder"
              @open-file="handleOpenFile"
              @context-menu="handleContextMenu"
            />
            <FileList
              v-else
              @open-folder="handleOpenFolder"
              @open-file="handleOpenFile"
              @context-menu="handleContextMenu"
            />
          </template>
        </div>
      </main>
    </div>

    <!-- Drag & Drop Full Viewport Overlay -->
    <DropZone />

    <!-- Custom Right-Click Context Menu -->
    <ContextMenu
      :is-open="contextMenu.isOpen"
      :position="contextMenu.position"
      :item="contextMenu.item"
      @action="handleContextAction"
      @close="closeContextMenu"
    />

    <!-- Dialogs & Modals -->
    <CreateFolderModal
      :is-open="isCreateFolderModalOpen"
      @close="isCreateFolderModalOpen = false"
    />
    <RenameModal
      :is-open="isRenameModalOpen"
      :item="activeItem"
      @close="isRenameModalOpen = false"
    />
    <MoveModal
      :is-open="isMoveModalOpen"
      :target-items="moveModalTargetItems"
      @close="isMoveModalOpen = false"
    />
    <ShareModal
      :is-open="isShareModalOpen"
      :item="activeItem"
      @close="isShareModalOpen = false"
    />
    <PreviewModal
      :is-open="isPreviewModalOpen"
      :file="activeItem"
      @close="isPreviewModalOpen = false"
    />

    <!-- Feedback UI Systems -->
    <ConfirmModal />
    <ConflictModal />
    <ToastContainer />
    <Snackbar />
    <UploadManager />
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue';
import { List, LayoutGrid } from 'lucide-vue-next';
import api from '../services/api';
import { useDriveStore } from '../stores/drive';
import { useFeedbackStore } from '../stores/feedback';
import { useHistoryStore } from '../stores/history';
import Navbar from '../components/layout/Navbar.vue';
import Sidebar from '../components/layout/Sidebar.vue';
import Breadcrumbs from '../components/layout/Breadcrumbs.vue';
import SelectionToolbar from '../components/layout/SelectionToolbar.vue';
import FileGrid from '../components/drive/FileGrid.vue';
import FileList from '../components/drive/FileList.vue';
import DropZone from '../components/drive/DropZone.vue';
import ContextMenu from '../components/drive/ContextMenu.vue';
import CreateFolderModal from '../components/modals/CreateFolderModal.vue';
import RenameModal from '../components/modals/RenameModal.vue';
import MoveModal from '../components/modals/MoveModal.vue';
import ShareModal from '../components/modals/ShareModal.vue';
import PreviewModal from '../components/modals/PreviewModal.vue';
import ConfirmModal from '../components/feedback/ConfirmModal.vue';
import ConflictModal from '../components/modals/ConflictModal.vue';
import ToastContainer from '../components/feedback/ToastContainer.vue';
import Snackbar from '../components/feedback/Snackbar.vue';
import UploadManager from '../components/feedback/UploadManager.vue';
import { useMarqueeSelection } from '../composables/useMarqueeSelection';

const drive = useDriveStore();
const feedback = useFeedbackStore();
const history = useHistoryStore();

const scrollContainerRef = ref(null);
const { isDragging, selectionBox } = useMarqueeSelection(scrollContainerRef);

const isMobileSidebarOpen = ref(false);
const isCreateFolderModalOpen = ref(false);
const isRenameModalOpen = ref(false);
const isMoveModalOpen = ref(false);
const moveModalTargetItems = ref([]);
const isShareModalOpen = ref(false);
const isPreviewModalOpen = ref(false);
const activeItem = ref(null);

const filterChips = [
  { id: 'all', label: 'All types' },
  { id: 'pdf', label: 'PDFs' },
  { id: 'doc', label: 'Documents' },
  { id: 'sheet', label: 'Spreadsheets' },
  { id: 'image', label: 'Photos & images' },
  { id: 'video', label: 'Videos' },
  { id: 'archive', label: 'Archives' },
];

const contextMenu = ref({
  isOpen: false,
  position: { x: 0, y: 0 },
  item: null,
});

const isTyping = (event) => {
  const active = document.activeElement;
  if (!active) return false;
  const tagName = active.tagName.toLowerCase();
  return (
    tagName === 'input' ||
    tagName === 'textarea' ||
    active.isContentEditable
  );
};

const handleOpenBatchMove = () => {
  moveModalTargetItems.value = [...drive.selectedItems];
  isMoveModalOpen.value = true;
};

const handleOpenRename = () => {
  if (drive.selectedItems.length === 1) {
    activeItem.value = drive.selectedItems[0];
    isRenameModalOpen.value = true;
  }
};

const handleOpenShare = () => {
  if (drive.selectedItems.length === 1) {
    activeItem.value = drive.selectedItems[0];
    isShareModalOpen.value = true;
  }
};

const handleOpenBatchDeleteConfirm = () => {
  const count = drive.selectedItems.length;
  const items = [...drive.selectedItems];
  feedback.openConfirm({
    title: 'Delete forever?',
    message: `${count} item${count > 1 ? 's' : ''} will be deleted forever and you won't be able to restore ${count > 1 ? 'them' : 'it'}.`,
    confirmText: 'Delete forever',
    isDanger: true,
    onConfirm: async () => {
      for (const item of items) {
        await drive.deleteForever(item);
      }
    },
  });
};

const handleKeyDown = (event) => {
  if (isTyping(event)) return;

  const isMac = typeof navigator !== 'undefined' && /Mac|iPod|iPhone|iPad/.test(navigator.platform);
  const modifier = isMac ? event.metaKey : event.ctrlKey;

  if (modifier && !event.altKey) {
    if (event.key === 'a' || event.key === 'A') {
      event.preventDefault();
      drive.selectAll();
    } else if (event.key === 'z' || event.key === 'Z') {
      if (event.shiftKey) {
        event.preventDefault();
        history.redo();
      } else {
        event.preventDefault();
        history.undo();
      }
    } else if (event.key === 'y' || event.key === 'Y') {
      event.preventDefault();
      history.redo();
    }
  } else if (event.key === 'Escape') {
    if (drive.selectedItems.length > 0) {
      event.preventDefault();
      drive.clearSelection();
    }
    closeContextMenu();
  } else if (event.key === 'Delete' || event.key === 'Backspace') {
    if (drive.selectedItems.length > 0) {
      event.preventDefault();
      if (drive.currentSection === 'trash') {
        handleOpenBatchDeleteConfirm();
      } else if (drive.currentSection !== 'shared') {
        drive.trashSelected();
      }
    }
  } else if (event.key === 'Enter') {
    if (drive.selectedItems.length === 1) {
      event.preventDefault();
      const single = drive.selectedItems[0];
      if (single.type === 'folder') {
        handleOpenFolder(single);
      } else {
        handleOpenFile(single);
      }
    }
  }
};

onMounted(() => {
  drive.fetchContents();
  window.addEventListener('keydown', handleKeyDown);
});

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeyDown);
});

const handleOpenFolder = (folder) => {
  if (drive.searchQuery) {
    drive.searchQuery = '';
  }
  drive.fetchContents(folder.id);
};

const handleOpenFile = (file) => {
  activeItem.value = file;
  isPreviewModalOpen.value = true;
};

const handleContextMenu = ({ event, item }) => {
  contextMenu.value = {
    isOpen: true,
    position: { x: event.clientX, y: event.clientY },
    item,
  };
};

const closeContextMenu = () => {
  contextMenu.value.isOpen = false;
};

const handleContextAction = async ({ action, item }) => {
  activeItem.value = item;
  switch (action) {
    case 'open':
      if (item.type === 'folder') {
        handleOpenFolder(item);
      } else {
        handleOpenFile(item);
      }
      break;
    case 'download':
      try {
        const baseURL = import.meta.env.VITE_API_URL || '/api';
        const { data } = await api.get(`/drive/files/${item.id}/media_token/`);
        const downloadUrl = `${baseURL}/drive/files/${item.id}/stream/?token=${encodeURIComponent(data.media_token)}`;
        const a = document.createElement('a');
        a.href = downloadUrl;
        a.download = item.name;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
      } catch (err) {
        feedback.showToast('error', 'Could not generate download link');
      }
      break;
    case 'share':
      if (drive.currentSection === 'shared' && item.effective_role !== 'editor' && item.effective_role !== 'owner') {
        feedback.showToast('info', 'Viewers cannot share this item');
        return;
      }
      isShareModalOpen.value = true;
      break;
    case 'star':
      drive.toggleStar(item);
      break;
    case 'rename':
      if (drive.currentSection === 'shared' && item.effective_role !== 'editor' && item.effective_role !== 'owner') {
        feedback.showToast('info', 'Viewers cannot rename this item');
        return;
      }
      isRenameModalOpen.value = true;
      break;
    case 'move':
      if (drive.currentSection === 'shared' && item.effective_role !== 'editor' && item.effective_role !== 'owner') return;
      moveModalTargetItems.value = [item];
      isMoveModalOpen.value = true;
      break;
    case 'trash':
      if (drive.currentSection === 'shared' && item.effective_role !== 'editor' && item.effective_role !== 'owner') return;
      drive.trashItem(item);
      break;
    case 'restore':
      drive.restoreItem(item);
      break;
    case 'delete_forever':
      feedback.openConfirm({
        title: 'Delete forever?',
        message: `"${item.name}" will be deleted forever and you won't be able to restore it.`,
        confirmText: 'Delete forever',
        isDanger: true,
        onConfirm: () => {
          drive.deleteForever(item);
        },
      });
      break;
  }
};
</script>
