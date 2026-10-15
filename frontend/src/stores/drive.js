import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import api from '../services/api';
import { useFeedbackStore } from './feedback';
import { useAuthStore } from './auth';
import { useHistoryStore } from './history';

let currentFetchId = 0;

export const useDriveStore = defineStore('drive', () => {
  const currentFolder = ref(null);
  const breadcrumbs = ref([]);
  const folders = ref([]);
  const files = ref([]);
  const loading = ref(false);
  const viewMode = ref('grid'); // 'grid' | 'list'
  const currentSection = ref('drive'); // 'drive' | 'starred' | 'trash'
  const selectedItems = ref([]); // array of { id, type: 'folder' | 'file' }
  const draggedItems = ref([]); // array of items currently being dragged
  const searchQuery = ref('');
  const selectedTypeFilter = ref('all'); // 'all' | 'pdf' | 'doc' | 'sheet' | 'image' | 'video' | 'archive'

  const feedback = useFeedbackStore();
  const auth = useAuthStore();
  const historyStore = useHistoryStore();

  let searchDebounceTimer = null;

  const fetchContents = async (folderId = null, silent = false) => {
    const fetchId = ++currentFetchId;
    if (!silent) {
      loading.value = true;
    }
    selectedItems.value = [];
    try {
      const isTrash = currentSection.value === 'trash';
      const isShared = currentSection.value === 'shared';
      const query = searchQuery.value.trim();
      
      let folderParams = { trashed: isTrash };
      let fileParams = { trashed: isTrash };

      if (isShared) {
        folderParams.shared = true;
        fileParams.shared = true;
      }

      if (query) {
        folderParams.search = query;
        fileParams.search = query;
      } else if (!isTrash) {
        if (folderId) {
          folderParams.parent = folderId;
          fileParams.folder = folderId;
        }
      }

      const [foldersRes, filesRes] = await Promise.all([
        api.get('/drive/folders/', { params: folderParams }),
        api.get('/drive/files/', { params: fileParams }),
      ]);

      if (fetchId !== currentFetchId) return;

      folders.value = foldersRes.data;
      files.value = filesRes.data;

      if (!query) {
        if (folderId) {
          const folderDetail = await api.get(`/drive/folders/${folderId}/`);
          if (fetchId !== currentFetchId) return;
          const newFolder = folderDetail.data;

          // Maintain breadcrumb trail
          const existingIdx = breadcrumbs.value.findIndex(b => b.id === folderId);
          if (existingIdx !== -1) {
            breadcrumbs.value = breadcrumbs.value.slice(0, existingIdx);
          } else if (currentFolder.value && newFolder.parent === currentFolder.value.id) {
            breadcrumbs.value.push({ id: currentFolder.value.id, name: currentFolder.value.name });
          } else if (!currentFolder.value) {
            breadcrumbs.value = [];
          } else if (newFolder.parent !== currentFolder.value?.id) {
            breadcrumbs.value = [];
          }

          currentFolder.value = newFolder;
        } else {
          currentFolder.value = null;
          breadcrumbs.value = [];
        }
      }

      auth.fetchMe(); // Refresh quota
    } catch (err) {
      if (fetchId !== currentFetchId) return;
      feedback.showToast('error', 'Failed to load drive contents');
    } finally {
      if (fetchId === currentFetchId) {
        loading.value = false;
      }
    }
  };

  const setSearchQuery = (query) => {
    searchQuery.value = query;
    if (searchDebounceTimer) clearTimeout(searchDebounceTimer);
    if (!query.trim()) {
      fetchContents(currentFolder.value?.id);
      return;
    }
    searchDebounceTimer = setTimeout(() => {
      fetchContents(currentFolder.value?.id);
    }, 300);
  };

  const clearSearch = () => {
    searchQuery.value = '';
    if (searchDebounceTimer) clearTimeout(searchDebounceTimer);
    fetchContents(currentFolder.value?.id);
  };

  const createFolder = async (name) => {
    try {
      const payload = {
        name: name.trim(),
        parent: currentFolder.value?.id || null,
      };
      await api.post('/drive/folders/', payload);
      feedback.showToast('success', `Folder "${name}" created`);
      await fetchContents(currentFolder.value?.id);
      return true;
    } catch (err) {
      feedback.showToast('error', err.response?.data?.detail || 'Failed to create folder');
      return false;
    }
  };

  const renameItem = async (item, newName, isUndoRedo = false) => {
    const oldName = item.name;
    try {
      if (item.type === 'folder') {
        await api.patch(`/drive/folders/${item.id}/`, { name: newName });
      } else {
        await api.post(`/drive/files/${item.id}/rename/`, { name: newName });
      }
      item.name = newName;
      if (currentFolder.value && currentFolder.value.id === item.id) {
        currentFolder.value.name = newName;
      }
      await fetchContents(currentFolder.value?.id, true);

      if (!isUndoRedo) {
        historyStore.recordAction({
          description: `Renamed to "${newName}"`,
          undoText: `Reverted name to "${oldName}"`,
          redoText: `Renamed to "${newName}"`,
          undo: async () => {
            await renameItem(item, oldName, true);
          },
          redo: async () => {
            await renameItem(item, newName, true);
          },
        });
      }
      return true;
    } catch (err) {
      feedback.showToast('error', err.response?.data?.detail || 'Failed to rename');
      return false;
    }
  };

  const moveItem = async (item, targetParentId, isUndoRedo = false) => {
    const oldParentId = item.type === 'folder'
      ? (item.parent !== undefined ? item.parent : (currentFolder.value?.id || null))
      : (item.folder !== undefined ? item.folder : (currentFolder.value?.id || null));

    try {
      if (item.type === 'folder') {
        await api.post(`/drive/folders/${item.id}/move/`, { target_parent_id: targetParentId });
        item.parent = targetParentId;
      } else {
        await api.post(`/drive/files/${item.id}/move/`, { target_folder_id: targetParentId });
        item.folder = targetParentId;
      }
      await fetchContents(currentFolder.value?.id);

      if (!isUndoRedo) {
        historyStore.recordAction({
          description: `Moved "${item.name}"`,
          undoText: `Moved "${item.name}" back`,
          redoText: `Moved "${item.name}"`,
          undo: async () => {
            await moveItem(item, oldParentId, true);
          },
          redo: async () => {
            await moveItem(item, targetParentId, true);
          },
        });
      }
      return true;
    } catch (err) {
      feedback.showToast('error', err.response?.data?.detail || 'Failed to move item');
      return false;
    }
  };

  const trashItem = async (item, isUndoRedo = false) => {
    try {
      if (item.type === 'folder') {
        await api.post(`/drive/folders/${item.id}/trash/`);
      } else {
        await api.post(`/drive/files/${item.id}/trash/`);
      }
      if (currentFolder.value && currentFolder.value.id === item.id) {
        await fetchContents(currentFolder.value.parent || null);
      } else {
        await fetchContents(currentFolder.value?.id);
      }

      if (!isUndoRedo) {
        historyStore.recordAction({
          description: `"${item.name}" moved to trash`,
          undoText: `"${item.name}" restored`,
          redoText: `"${item.name}" moved to trash`,
          undo: async () => {
            await restoreItem(item, true);
          },
          redo: async () => {
            await trashItem(item, true);
          },
        });
      }
      return true;
    } catch (err) {
      feedback.showToast('error', 'Failed to move to trash');
      return false;
    }
  };

  const restoreItem = async (item, isUndoRedo = false) => {
    try {
      if (item.type === 'folder') {
        await api.post(`/drive/folders/${item.id}/restore/`);
      } else {
        await api.post(`/drive/files/${item.id}/restore/`);
      }
      await fetchContents(currentFolder.value?.id);

      if (!isUndoRedo) {
        historyStore.recordAction({
          description: `"${item.name}" restored`,
          undoText: `"${item.name}" moved back to trash`,
          redoText: `"${item.name}" restored`,
          undo: async () => {
            await trashItem(item, true);
          },
          redo: async () => {
            await restoreItem(item, true);
          },
        });
      }
      return true;
    } catch (err) {
      feedback.showToast('error', 'Failed to restore item');
      return false;
    }
  };

  const deleteForever = async (item) => {
    try {
      if (item.type === 'folder') {
        await api.delete(`/drive/folders/${item.id}/`);
      } else {
        await api.delete(`/drive/files/${item.id}/`);
      }
      historyStore.clear();
      feedback.showToast('info', `"${item.name}" permanently deleted`);
      await fetchContents(currentFolder.value?.id);
      auth.fetchMe();
      return true;
    } catch (err) {
      feedback.showToast('error', err.response?.data?.detail || 'Failed to delete');
      return false;
    }
  };

  const toggleStar = async (item) => {
    try {
      if (item.type === 'folder') {
        const { data } = await api.post(`/drive/folders/${item.id}/toggle_star/`);
        item.is_starred = data.is_starred;
      } else {
        const { data } = await api.post(`/drive/files/${item.id}/toggle_star/`);
        item.is_starred = data.is_starred;
      }
      feedback.showToast('info', item.is_starred ? 'Added to Starred' : 'Removed from Starred');
    } catch (err) {
      feedback.showToast('error', 'Could not update star');
    }
  };

  const lastSelectedItem = ref(null);

  const isSelected = (item) => {
    return selectedItems.value.some(i => i.id === item.id);
  };

  const selectItem = (item, { isToggle = false, isRange = false, allItems = [] } = {}) => {
    if (isToggle) {
      const idx = selectedItems.value.findIndex(i => i.id === item.id);
      if (idx !== -1) {
        selectedItems.value.splice(idx, 1);
      } else {
        selectedItems.value.push(item);
      }
      lastSelectedItem.value = item;
    } else if (isRange && lastSelectedItem.value && allItems.length > 0) {
      const fromIdx = allItems.findIndex(i => i.id === lastSelectedItem.value.id);
      const toIdx = allItems.findIndex(i => i.id === item.id);
      if (fromIdx !== -1 && toIdx !== -1) {
        const start = Math.min(fromIdx, toIdx);
        const end = Math.max(fromIdx, toIdx);
        const range = allItems.slice(start, end + 1);
        const combined = [...selectedItems.value];
        for (const it of range) {
          if (!combined.some(c => c.id === it.id)) {
            combined.push(it);
          }
        }
        selectedItems.value = combined;
      } else {
        selectedItems.value = [item];
        lastSelectedItem.value = item;
      }
    } else {
      selectedItems.value = [item];
      lastSelectedItem.value = item;
    }
  };

  const selectAll = (items = []) => {
    if (items.length > 0) {
      selectedItems.value = [...items];
    } else {
      const all = [
        ...folders.value.map(f => ({ ...f, type: 'folder' })),
        ...files.value.map(f => ({ ...f, type: 'file' })),
      ];
      selectedItems.value = all;
    }
  };

  const clearSelection = () => {
    selectedItems.value = [];
    lastSelectedItem.value = null;
  };

  const trashSelected = async () => {
    if (selectedItems.value.length === 0) return;
    const itemsToTrash = [...selectedItems.value];
    const count = itemsToTrash.length;
    clearSelection();

    try {
      await Promise.all(
        itemsToTrash.map(item =>
          item.type === 'folder'
            ? api.post(`/drive/folders/${item.id}/trash/`)
            : api.post(`/drive/files/${item.id}/trash/`)
        )
      );
      await fetchContents(currentFolder.value?.id);

      historyStore.recordAction({
        description: count === 1 ? `"${itemsToTrash[0].name}" moved to trash` : `${count} items moved to trash`,
        undoText: count === 1 ? `"${itemsToTrash[0].name}" restored` : `${count} items restored`,
        redoText: count === 1 ? `"${itemsToTrash[0].name}" moved to trash` : `${count} items moved to trash`,
        undo: async () => {
          await Promise.all(
            itemsToTrash.map(item =>
              item.type === 'folder'
                ? api.post(`/drive/folders/${item.id}/restore/`)
                : api.post(`/drive/files/${item.id}/restore/`)
            )
          );
          await fetchContents(currentFolder.value?.id);
        },
        redo: async () => {
          await Promise.all(
            itemsToTrash.map(item =>
              item.type === 'folder'
                ? api.post(`/drive/folders/${item.id}/trash/`)
                : api.post(`/drive/files/${item.id}/trash/`)
            )
          );
          await fetchContents(currentFolder.value?.id);
        },
      });
      return true;
    } catch (err) {
      feedback.showToast('error', 'Failed to move selected items to trash');
      return false;
    }
  };

  const restoreSelected = async () => {
    if (selectedItems.value.length === 0) return;
    const itemsToRestore = [...selectedItems.value];
    const count = itemsToRestore.length;
    clearSelection();

    try {
      await Promise.all(
        itemsToRestore.map(item =>
          item.type === 'folder'
            ? api.post(`/drive/folders/${item.id}/restore/`)
            : api.post(`/drive/files/${item.id}/restore/`)
        )
      );
      await fetchContents(currentFolder.value?.id);

      historyStore.recordAction({
        description: count === 1 ? `"${itemsToRestore[0].name}" restored` : `${count} items restored`,
        undoText: count === 1 ? `"${itemsToRestore[0].name}" moved back to trash` : `${count} items moved back to trash`,
        redoText: count === 1 ? `"${itemsToRestore[0].name}" restored` : `${count} items restored`,
        undo: async () => {
          await Promise.all(
            itemsToRestore.map(item =>
              item.type === 'folder'
                ? api.post(`/drive/folders/${item.id}/trash/`)
                : api.post(`/drive/files/${item.id}/trash/`)
            )
          );
          await fetchContents(currentFolder.value?.id);
        },
        redo: async () => {
          await Promise.all(
            itemsToRestore.map(item =>
              item.type === 'folder'
                ? api.post(`/drive/folders/${item.id}/restore/`)
                : api.post(`/drive/files/${item.id}/restore/`)
            )
          );
          await fetchContents(currentFolder.value?.id);
        },
      });
      return true;
    } catch (err) {
      feedback.showToast('error', 'Failed to restore selected items');
      return false;
    }
  };

  const starSelected = async () => {
    if (selectedItems.value.length === 0) return;
    const items = [...selectedItems.value];
    const shouldStar = items.some(i => !i.is_starred);
    try {
      await Promise.all(
        items.map(async item => {
          if (item.is_starred !== shouldStar) {
            if (item.type === 'folder') {
              await api.post(`/drive/folders/${item.id}/toggle_star/`);
            } else {
              await api.post(`/drive/files/${item.id}/toggle_star/`);
            }
            item.is_starred = shouldStar;
          }
        })
      );
      feedback.showToast('info', shouldStar ? 'Added to Starred' : 'Removed from Starred');
    } catch (err) {
      feedback.showToast('error', 'Failed to update star');
    }
  };

  const moveSelected = async (targetParentId, customItems = null) => {
    const rawItems = customItems && customItems.length > 0 ? customItems : selectedItems.value;
    if (!rawItems || rawItems.length === 0) return false;

    // Cycle protection: cannot move a folder into itself
    const itemsToMove = rawItems.filter(item => !(item.type === 'folder' && item.id === targetParentId));
    if (itemsToMove.length === 0) return false;

    const count = itemsToMove.length;
    const previousParents = itemsToMove.map(item => ({
      item,
      oldParentId: item.type === 'folder'
        ? (item.parent !== undefined ? item.parent : (currentFolder.value?.id || null))
        : (item.folder !== undefined ? item.folder : (currentFolder.value?.id || null)),
    }));

    clearSelection();
    draggedItems.value = [];

    try {
      await Promise.all(
        itemsToMove.map(item =>
          item.type === 'folder'
            ? api.post(`/drive/folders/${item.id}/move/`, { target_parent_id: targetParentId })
            : api.post(`/drive/files/${item.id}/move/`, { target_folder_id: targetParentId })
        )
      );
      await fetchContents(currentFolder.value?.id);

      historyStore.recordAction({
        description: count === 1 ? `Moved "${itemsToMove[0].name}"` : `Moved ${count} items`,
        undoText: count === 1 ? `Moved "${itemsToMove[0].name}" back` : `Moved ${count} items back`,
        redoText: count === 1 ? `Moved "${itemsToMove[0].name}"` : `Moved ${count} items`,
        undo: async () => {
          await Promise.all(
            previousParents.map(({ item, oldParentId }) =>
              item.type === 'folder'
                ? api.post(`/drive/folders/${item.id}/move/`, { target_parent_id: oldParentId })
                : api.post(`/drive/files/${item.id}/move/`, { target_folder_id: oldParentId })
            )
          );
          await fetchContents(currentFolder.value?.id);
        },
        redo: async () => {
          await Promise.all(
            itemsToMove.map(item =>
              item.type === 'folder'
                ? api.post(`/drive/folders/${item.id}/move/`, { target_parent_id: targetParentId })
                : api.post(`/drive/files/${item.id}/move/`, { target_folder_id: targetParentId })
            )
          );
          await fetchContents(currentFolder.value?.id);
        },
      });
      return true;
    } catch (err) {
      feedback.showToast('error', 'Failed to move items');
      return false;
    }
  };

  const downloadSelected = async () => {
    if (selectedItems.value.length === 0) return;
    const filesToDownload = selectedItems.value.filter(i => i.type === 'file');
    if (filesToDownload.length === 0) {
      feedback.showToast('info', 'Folders cannot be directly downloaded');
      return;
    }

    const baseURL = import.meta.env.VITE_API_URL || '/api';
    for (const file of filesToDownload) {
      try {
        const { data } = await api.get(`/drive/files/${file.id}/media_token/`);
        const downloadUrl = `${baseURL}/drive/files/${file.id}/stream/?token=${encodeURIComponent(data.media_token)}&download=1`;
        const a = document.createElement('a');
        a.href = downloadUrl;
        a.download = file.name;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
      } catch (err) {
        feedback.showToast('error', `Failed to download "${file.name}"`);
      }
    }
  };

  return {
    currentFolder,
    breadcrumbs,
    folders,
    files,
    loading,
    viewMode,
    currentSection,
    selectedItems,
    draggedItems,
    lastSelectedItem,
    isSelected,
    selectItem,
    selectAll,
    clearSelection,
    trashSelected,
    restoreSelected,
    starSelected,
    moveSelected,
    downloadSelected,
    searchQuery,
    selectedTypeFilter,
    setSearchQuery,
    clearSearch,
    fetchContents,
    createFolder,
    renameItem,
    moveItem,
    trashItem,
    restoreItem,
    deleteForever,
    toggleStar,
  };
});
