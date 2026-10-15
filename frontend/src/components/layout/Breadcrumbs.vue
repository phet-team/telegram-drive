<template>
  <!-- Search Results Breadcrumb State -->
  <div v-if="drive.searchQuery.trim()" class="flex items-center gap-2 text-[#1f1f1f] py-0.5 sm:py-1 select-none min-w-0 overflow-x-auto">
    <div class="flex items-center gap-2 px-1 py-1 text-lg sm:text-2xl font-normal tracking-tight truncate">
      <Search class="w-5 h-5 text-[#444746] shrink-0" />
      <span>Search results</span>
      <span class="text-sm sm:text-base font-normal text-[#747775] truncate">for "{{ drive.searchQuery }}"</span>
    </div>
    <button
      type="button"
      class="text-xs font-medium text-[#0b57d0] hover:bg-[#d3e3fd]/50 px-2.5 py-1 rounded-full transition-colors cursor-pointer shrink-0"
      @click="drive.clearSearch()"
    >
      Clear
    </button>
  </div>

  <!-- Normal Navigation Breadcrumbs -->
  <div v-else class="flex items-center gap-1 sm:gap-1.5 text-[#1f1f1f] py-0.5 sm:py-1 select-none min-w-0 overflow-x-auto">
    <!-- Root / Section Title (Drop target if inside subfolder) -->
    <button
      type="button"
      :class="[
        'px-2 sm:px-3 py-1 sm:py-1.5 rounded-full transition-all flex items-center gap-1.5 text-lg sm:text-2xl font-normal tracking-tight cursor-pointer truncate shrink-0',
        activeDropTargetId === 'root'
          ? 'bg-[#c2e7ff] text-[#0b57d0] ring-2 ring-[#0b57d0] scale-105 shadow-sm'
          : 'hover:bg-[#eaebef]'
      ]"
      @click="handleNavigate(null)"
      @dragover="handleDragOver(null, $event)"
      @dragleave="handleDragLeave('root', $event)"
      @drop="handleDrop(null, rootTitle, $event)"
    >
      <span>{{ rootTitle }}</span>
    </button>

    <!-- Ancestor Path (Drop targets) -->
    <template v-for="crumb in drive.breadcrumbs" :key="crumb.id">
      <ChevronRight class="w-3.5 h-3.5 sm:w-4 sm:h-4 text-[#747775] shrink-0" />
      <button
        type="button"
        :class="[
          'px-2 sm:px-3 py-1 sm:py-1.5 rounded-full transition-all text-base sm:text-xl font-normal cursor-pointer truncate max-w-[120px] xs:max-w-xs shrink-0',
          activeDropTargetId === crumb.id
            ? 'bg-[#c2e7ff] text-[#0b57d0] ring-2 ring-[#0b57d0] scale-105 shadow-sm'
            : 'text-[#444746] hover:text-[#1f1f1f] hover:bg-[#eaebef]'
        ]"
        @click="handleNavigate(crumb.id)"
        @dragover="handleDragOver(crumb.id, $event)"
        @dragleave="handleDragLeave(crumb.id, $event)"
        @drop="handleDrop(crumb.id, crumb.name, $event)"
      >
        {{ crumb.name }}
      </button>
    </template>

    <!-- Current active subfolder with Google Drive Dropdown Menu -->
    <template v-if="drive.currentFolder">
      <ChevronRight class="w-3.5 h-3.5 sm:w-4 sm:h-4 text-[#747775] shrink-0" />
      <button
        ref="dropdownButtonRef"
        type="button"
        :class="[
          'px-2 sm:px-3 py-1 sm:py-1.5 rounded-full transition-all flex items-center gap-1.5 text-base sm:text-xl font-medium cursor-pointer truncate max-w-[140px] xs:max-w-xs shrink-0',
          isDropdownOpen
            ? 'bg-[#eaebef] text-[#1f1f1f]'
            : 'text-[#1f1f1f] hover:bg-[#eaebef]'
        ]"
        @click.stop="toggleDropdown"
        @contextmenu.prevent.stop="toggleDropdown"
        :title="drive.currentFolder.name + ' options'"
      >
        <span class="truncate">{{ drive.currentFolder.name }}</span>
        <ChevronDown class="w-4 h-4 text-[#444746] shrink-0 transition-transform duration-200" :class="{ 'rotate-180': isDropdownOpen }" />
      </button>

      <!-- Teleported Dropdown Menu: immune to parent overflow/clipping -->
      <Teleport to="body">
        <div
          v-if="isDropdownOpen"
          ref="dropdownMenuRef"
          :style="dropdownStyle"
          class="fixed z-[9999] w-56 bg-white rounded-2xl shadow-[0_4px_24px_rgba(0,0,0,0.18)] border border-gray-150 py-2 text-sm text-[#1f1f1f] select-none animate-in fade-in zoom-in-95 duration-100"
          @click.stop
        >
          <div class="px-4 py-1.5 mb-1 border-b border-gray-100 flex items-center gap-2 text-xs text-[#747775] truncate">
            <span class="font-medium text-[#1f1f1f] truncate">{{ drive.currentFolder.name }}</span>
          </div>

          <button
            type="button"
            class="w-full text-left px-4 py-2 hover:bg-[#f0f4f9] flex items-center gap-3 transition-colors text-[13.5px] font-medium text-[#1f1f1f] cursor-pointer"
            @click="triggerAction('share')"
          >
            <UserPlus class="w-4 h-4 text-[#444746] shrink-0" />
            <span>Share</span>
          </button>

          <button
            type="button"
            class="w-full text-left px-4 py-2 hover:bg-[#f0f4f9] flex items-center gap-3 transition-colors text-[13.5px] font-medium text-[#1f1f1f] cursor-pointer"
            @click="triggerAction('rename')"
          >
            <Edit2 class="w-4 h-4 text-[#444746] shrink-0" />
            <span>Rename</span>
          </button>

          <button
            type="button"
            class="w-full text-left px-4 py-2 hover:bg-[#f0f4f9] flex items-center gap-3 transition-colors text-[13.5px] font-medium text-[#1f1f1f] cursor-pointer"
            @click="triggerAction('star')"
          >
            <Star
              class="w-4 h-4 shrink-0"
              :class="drive.currentFolder.is_starred ? 'text-amber-500 fill-amber-500' : 'text-[#444746]'"
            />
            <span>{{ drive.currentFolder.is_starred ? 'Remove from Starred' : 'Add to Starred' }}</span>
          </button>

          <div class="h-px bg-gray-150 my-1"></div>

          <button
            type="button"
            class="w-full text-left px-4 py-2 hover:bg-rose-50 flex items-center gap-3 transition-colors text-[13.5px] font-medium text-rose-600 cursor-pointer"
            @click="triggerAction('trash')"
          >
            <Trash2 class="w-4 h-4 text-rose-600 shrink-0" />
            <span>Move to trash</span>
          </button>
        </div>
      </Teleport>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue';
import { ChevronRight, Search, ChevronDown, UserPlus, Edit2, Star, Trash2 } from 'lucide-vue-next';
import { useDriveStore } from '../../stores/drive';
import { useFeedbackStore } from '../../stores/feedback';

const emit = defineEmits(['action']);

const drive = useDriveStore();
const feedback = useFeedbackStore();

const activeDropTargetId = ref(null);
const dropdownButtonRef = ref(null);
const dropdownMenuRef = ref(null);
const isDropdownOpen = ref(false);
const dropdownStyle = ref({});

const updateDropdownPosition = () => {
  if (!dropdownButtonRef.value) return;
  const rect = dropdownButtonRef.value.getBoundingClientRect();
  const menuWidth = 224; // w-56
  
  let left = rect.left;
  if (left + menuWidth > window.innerWidth - 12) {
    left = window.innerWidth - menuWidth - 12;
  }
  if (left < 12) {
    left = 12;
  }

  dropdownStyle.value = {
    top: `${rect.bottom + 6}px`,
    left: `${left}px`,
  };
};

const toggleDropdown = () => {
  if (!isDropdownOpen.value) {
    updateDropdownPosition();
    isDropdownOpen.value = true;
  } else {
    isDropdownOpen.value = false;
  }
};

const handleDocumentClick = (e) => {
  if (!isDropdownOpen.value) return;
  if (
    dropdownButtonRef.value?.contains(e.target) ||
    dropdownMenuRef.value?.contains(e.target)
  ) {
    return;
  }
  isDropdownOpen.value = false;
};

const handleScrollOrResize = () => {
  if (isDropdownOpen.value) {
    updateDropdownPosition();
  }
};

onMounted(() => {
  document.addEventListener('click', handleDocumentClick);
  window.addEventListener('resize', handleScrollOrResize);
  window.addEventListener('scroll', handleScrollOrResize, true);
});

onUnmounted(() => {
  document.removeEventListener('click', handleDocumentClick);
  window.removeEventListener('resize', handleScrollOrResize);
  window.removeEventListener('scroll', handleScrollOrResize, true);
});

watch(() => drive.currentFolder?.id, () => {
  isDropdownOpen.value = false;
});

const triggerAction = (action) => {
  isDropdownOpen.value = false;
  emit('action', { action, item: { ...drive.currentFolder, type: 'folder' } });
};

const rootTitle = computed(() => {
  if (drive.currentSection === 'trash') return 'Trash';
  if (drive.currentSection === 'starred') return 'Starred';
  if (drive.currentSection === 'shared') return 'Shared with me';
  return 'My Drive';
});

const handleNavigate = (folderId) => {
  drive.fetchContents(folderId);
};

const isValidDrop = (targetFolderId) => {
  if (drive.draggedItems.length === 0) return false;
  // If target is root, only valid if we are currently inside a folder
  if (targetFolderId === null) {
    return drive.currentFolder !== null;
  }
  // Cannot drop into current folder (items already here)
  if (drive.currentFolder && drive.currentFolder.id === targetFolderId) {
    return false;
  }
  // Cannot drop a folder into itself
  const hasSelf = drive.draggedItems.some(i => i.type === 'folder' && i.id === targetFolderId);
  return !hasSelf;
};

const handleDragOver = (targetFolderId, e) => {
  if (!isValidDrop(targetFolderId)) return;
  e.preventDefault();
  e.dataTransfer.dropEffect = 'move';
  activeDropTargetId.value = targetFolderId ?? 'root';
};

const handleDragLeave = (targetId, e) => {
  // Only clear if mouse actually left the button element
  if (!e.currentTarget.contains(e.relatedTarget)) {
    if (activeDropTargetId.value === targetId) {
      activeDropTargetId.value = null;
    }
  }
};

const handleDrop = async (targetFolderId, targetName, e) => {
  e.preventDefault();
  activeDropTargetId.value = null;
  if (!isValidDrop(targetFolderId)) return;

  const count = drive.draggedItems.length;
  const success = await drive.moveSelected(targetFolderId, drive.draggedItems);
  if (success) {
    feedback.showToast('info', `Moved ${count} item${count > 1 ? 's' : ''} to "${targetName}"`);
  }
};
</script>
