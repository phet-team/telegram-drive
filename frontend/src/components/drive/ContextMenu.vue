<template>
  <div v-if="isOpen">
    <!-- Mobile Backdrop -->
    <div
      class="fixed inset-0 bg-black/40 backdrop-blur-xs z-50 sm:hidden animate-in fade-in duration-150"
      @click="emit('close')"
    ></div>

    <!-- Mobile Bottom Sheet (Google Drive Mobile Style) -->
    <div
      class="fixed inset-x-0 bottom-0 z-50 bg-white rounded-t-3xl shadow-2xl pb-[max(1.5rem,env(safe-area-inset-bottom,1.5rem))] pt-3 px-4 sm:hidden animate-in slide-in-from-bottom duration-200 max-h-[85vh] overflow-y-auto overscroll-contain select-none"
      @click.stop
    >
      <!-- Drag Pill Handle -->
      <div class="w-10 h-1 bg-gray-300 rounded-full mx-auto mb-3"></div>

      <!-- Header: File Icon + Info -->
      <div class="flex items-center gap-3 pb-3 mb-2 border-b border-gray-150 px-2">
        <FileIcon :mime-type="item?.mime_type" :is-folder="item?.type === 'folder'" size="md" class="shrink-0" />
        <div class="min-w-0 flex-1">
          <div class="text-[15px] font-medium text-[#1f1f1f] truncate">{{ item?.name }}</div>
          <div class="text-xs text-[#747775] mt-0.5">
            <template v-if="item?.size">{{ formatBytes(item?.size) }}</template>
            <template v-else-if="item?.type === 'folder'">Folder</template>
            <template v-if="item?.owner_name"> • {{ item.owner_name }}</template>
          </div>
        </div>
      </div>

      <!-- Action Items for Mobile -->
      <div class="flex flex-col gap-0.5">
        <template v-if="!item?.is_trashed">
          <button
            type="button"
            class="w-full text-left px-4 py-3 hover:bg-[#f0f4f9] active:bg-[#e4ebf7] rounded-xl flex items-center gap-4 transition-colors text-[15px] font-medium text-[#1f1f1f] cursor-pointer"
            @click="handleAction('open')"
          >
            <Eye class="w-5 h-5 text-[#444746]" />
            <span>Open</span>
          </button>

          <button
            v-if="item?.type === 'file'"
            type="button"
            class="w-full text-left px-4 py-3 hover:bg-[#f0f4f9] active:bg-[#e4ebf7] rounded-xl flex items-center gap-4 transition-colors text-[15px] font-medium text-[#1f1f1f] cursor-pointer"
            @click="handleAction('download')"
          >
            <Download class="w-5 h-5 text-[#444746]" />
            <span>Download</span>
          </button>

          <button
            v-if="canShare"
            type="button"
            class="w-full text-left px-4 py-3 hover:bg-[#f0f4f9] active:bg-[#e4ebf7] rounded-xl flex items-center gap-4 transition-colors text-[15px] font-medium text-[#1f1f1f] cursor-pointer"
            @click="handleAction('share')"
          >
            <Share2 class="w-5 h-5 text-[#444746]" />
            <span>Share</span>
          </button>

          <button
            type="button"
            class="w-full text-left px-4 py-3 hover:bg-[#f0f4f9] active:bg-[#e4ebf7] rounded-xl flex items-center gap-4 transition-colors text-[15px] font-medium text-[#1f1f1f] cursor-pointer"
            @click="handleAction('star')"
          >
            <Star
              class="w-5 h-5"
              :class="item?.is_starred ? 'fill-[#f4b400] text-[#f4b400]' : 'text-[#444746]'"
            />
            <span>{{ item?.is_starred ? 'Remove from starred' : 'Add to starred' }}</span>
          </button>

          <button
            v-if="canRename"
            type="button"
            class="w-full text-left px-4 py-3 hover:bg-[#f0f4f9] active:bg-[#e4ebf7] rounded-xl flex items-center gap-4 transition-colors text-[15px] font-medium text-[#1f1f1f] cursor-pointer"
            @click="handleAction('rename')"
          >
            <Edit3 class="w-5 h-5 text-[#444746]" />
            <span>Rename</span>
          </button>

          <button
            v-if="canMove"
            type="button"
            class="w-full text-left px-4 py-3 hover:bg-[#f0f4f9] active:bg-[#e4ebf7] rounded-xl flex items-center gap-4 transition-colors text-[15px] font-medium text-[#1f1f1f] cursor-pointer"
            @click="handleAction('move')"
          >
            <FolderInput class="w-5 h-5 text-[#444746]" />
            <span>Move to...</span>
          </button>

          <div v-if="canTrash" class="h-px bg-gray-150 my-1.5 mx-2"></div>

          <button
            v-if="canTrash"
            type="button"
            class="w-full text-left px-4 py-3 hover:bg-red-50 active:bg-red-100 rounded-xl text-[#d93025] flex items-center gap-4 transition-colors text-[15px] font-medium cursor-pointer"
            @click="handleAction('trash')"
          >
            <Trash2 class="w-5 h-5 text-[#d93025]" />
            <span>Move to trash</span>
          </button>
        </template>

        <template v-else>
          <button
            type="button"
            class="w-full text-left px-4 py-3 hover:bg-[#f0f4f9] active:bg-[#e4ebf7] rounded-xl flex items-center gap-4 transition-colors text-[15px] font-medium text-[#1f1f1f] cursor-pointer"
            @click="handleAction('restore')"
          >
            <RotateCcw class="w-5 h-5 text-[#444746]" />
            <span>Restore</span>
          </button>

          <div class="h-px bg-gray-150 my-1.5 mx-2"></div>

          <button
            type="button"
            class="w-full text-left px-4 py-3 hover:bg-red-50 active:bg-red-100 rounded-xl text-[#d93025] flex items-center gap-4 transition-colors text-[15px] font-medium cursor-pointer"
            @click="handleAction('delete_forever')"
          >
            <AlertTriangle class="w-5 h-5 text-[#d93025]" />
            <span>Delete forever</span>
          </button>
        </template>
      </div>
    </div>

    <!-- Desktop Floating Context Menu (sm and larger) -->
    <div
      class="hidden sm:block fixed z-50 bg-white rounded-2xl shadow-[0_4px_24px_rgba(0,0,0,0.18)] border border-gray-150 py-2 w-60 text-sm text-[#1f1f1f] select-none animate-in fade-in zoom-in-95 duration-100"
      :style="menuStyle"
      @click.stop
    >
      <!-- Not Trashed Items -->
      <template v-if="!item?.is_trashed">
        <button
          type="button"
          class="w-full text-left px-4 py-2 hover:bg-[#f0f4f9] flex items-center gap-3 transition-colors text-[13.5px] font-medium cursor-pointer"
          @click="handleAction('open')"
        >
          <Eye class="w-4 h-4 text-[#444746]" />
          <span>Open</span>
        </button>

        <button
          v-if="item?.type === 'file'"
          type="button"
          class="w-full text-left px-4 py-2 hover:bg-[#f0f4f9] flex items-center gap-3 transition-colors text-[13.5px] font-medium cursor-pointer"
          @click="handleAction('download')"
        >
          <Download class="w-4 h-4 text-[#444746]" />
          <span>Download</span>
        </button>

        <button
          v-if="canShare"
          type="button"
          class="w-full text-left px-4 py-2 hover:bg-[#f0f4f9] flex items-center gap-3 transition-colors text-[13.5px] font-medium cursor-pointer"
          @click="handleAction('share')"
        >
          <Share2 class="w-4 h-4 text-[#444746]" />
          <span>Share</span>
        </button>

        <button
          type="button"
          class="w-full text-left px-4 py-2 hover:bg-[#f0f4f9] flex items-center gap-3 transition-colors text-[13.5px] font-medium cursor-pointer"
          @click="handleAction('star')"
        >
          <Star
            class="w-4 h-4"
            :class="item?.is_starred ? 'fill-[#f4b400] text-[#f4b400]' : 'text-[#444746]'"
          />
          <span>{{ item?.is_starred ? 'Remove from starred' : 'Add to starred' }}</span>
        </button>

        <button
          v-if="canRename"
          type="button"
          class="w-full text-left px-4 py-2 hover:bg-[#f0f4f9] flex items-center gap-3 transition-colors text-[13.5px] font-medium cursor-pointer"
          @click="handleAction('rename')"
        >
          <Edit3 class="w-4 h-4 text-[#444746]" />
          <span>Rename</span>
        </button>

        <button
          v-if="canMove"
          type="button"
          class="w-full text-left px-4 py-2 hover:bg-[#f0f4f9] flex items-center gap-3 transition-colors text-[13.5px] font-medium cursor-pointer"
          @click="handleAction('move')"
        >
          <FolderInput class="w-4 h-4 text-[#444746]" />
          <span>Move to...</span>
        </button>

        <div v-if="canTrash" class="h-px bg-gray-150 my-1.5"></div>

        <button
          v-if="canTrash"
          type="button"
          class="w-full text-left px-4 py-2 hover:bg-red-50 text-[#d93025] flex items-center gap-3 transition-colors text-[13.5px] font-medium cursor-pointer"
          @click="handleAction('trash')"
        >
          <Trash2 class="w-4 h-4 text-[#d93025]" />
          <span>Move to trash</span>
        </button>
      </template>

      <!-- Trashed Items -->
      <template v-else>
        <button
          type="button"
          class="w-full text-left px-4 py-2 hover:bg-[#f0f4f9] flex items-center gap-3 transition-colors text-[13.5px] font-medium cursor-pointer"
          @click="handleAction('restore')"
        >
          <RotateCcw class="w-4 h-4 text-[#444746]" />
          <span>Restore</span>
        </button>

        <div class="h-px bg-gray-150 my-1.5"></div>

        <button
          type="button"
          class="w-full text-left px-4 py-2 hover:bg-red-50 text-[#d93025] flex items-center gap-3 transition-colors text-[13.5px] font-medium cursor-pointer"
          @click="handleAction('delete_forever')"
        >
          <AlertTriangle class="w-4 h-4 text-[#d93025]" />
          <span>Delete forever</span>
        </button>
      </template>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue';
import { Eye, Download, Share2, Star, Edit3, FolderInput, Trash2, RotateCcw, AlertTriangle } from 'lucide-vue-next';
import FileIcon from './FileIcon.vue';
import { useDriveStore } from '../../stores/drive';
import { useAuthStore } from '../../stores/auth';

const props = defineProps({
  isOpen: Boolean,
  position: Object,
  item: Object,
});
const emit = defineEmits(['action', 'close']);

const drive = useDriveStore();
const auth = useAuthStore();

const isOwner = computed(() => {
  if (props.item?.effective_role) {
    return props.item.effective_role === 'owner';
  }
  if (auth.user?.email && props.item?.owner_email) {
    return props.item.owner_email.toLowerCase() === auth.user.email.toLowerCase();
  }
  return true;
});

const canEdit = computed(() => {
  return isOwner.value || props.item?.effective_role === 'editor';
});

// Restrict actions: in "Shared with me", users cannot Share, Rename, or Trash
const canShare = computed(() => isOwner.value && drive.currentSection !== 'shared');
const canRename = computed(() => canEdit.value && drive.currentSection !== 'shared');
const canMove = computed(() => canEdit.value && drive.currentSection !== 'shared');
const canTrash = computed(() => isOwner.value && drive.currentSection !== 'shared');

const menuStyle = computed(() => {
  if (!props.position) return {};
  const menuWidth = 240;
  const menuHeight = 280;
  const x = Math.min(props.position.x, window.innerWidth - menuWidth - 10);
  const y = Math.min(props.position.y, window.innerHeight - menuHeight - 10);
  return {
    top: `${Math.max(10, y)}px`,
    left: `${Math.max(10, x)}px`,
  };
});

const handleAction = (actionName) => {
  emit('action', { action: actionName, item: props.item });
  emit('close');
};

const formatBytes = (bytes) => {
  if (!bytes) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
};
</script>
