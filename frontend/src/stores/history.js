import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import { useFeedbackStore } from './feedback';

export const useHistoryStore = defineStore('history', () => {
  const undoStack = ref([]);
  const redoStack = ref([]);
  const maxStackSize = 30;
  const isExecuting = ref(false);

  const feedback = useFeedbackStore();

  const canUndo = computed(() => undoStack.value.length > 0);
  const canRedo = computed(() => redoStack.value.length > 0);

  /**
   * Registers a new reversible user action
   * @param {Object} action - { description, undoText, redoText, undo: AsyncFunction, redo: AsyncFunction }
   */
  const recordAction = (action) => {
    undoStack.value.push(action);
    if (undoStack.value.length > maxStackSize) {
      undoStack.value.shift();
    }
    // Performing a new user action invalidates the redo stack
    redoStack.value = [];

    if (action.description) {
      feedback.showSnackbar(
        action.description,
        'Undo',
        () => undo(),
        6000
      );
    }
  };

  const undo = async () => {
    if (!canUndo.value || isExecuting.value) return;
    const action = undoStack.value.pop();
    isExecuting.value = true;
    try {
      await action.undo();
      redoStack.value.push(action);
      feedback.showSnackbar(
        action.undoText || 'Action undone',
        'Redo',
        () => redo(),
        6000
      );
    } catch (err) {
      feedback.showToast('error', 'Failed to undo action');
    } finally {
      isExecuting.value = false;
    }
  };

  const redo = async () => {
    if (!canRedo.value || isExecuting.value) return;
    const action = redoStack.value.pop();
    isExecuting.value = true;
    try {
      await action.redo();
      undoStack.value.push(action);
      feedback.showSnackbar(
        action.redoText || 'Action redone',
        'Undo',
        () => undo(),
        6000
      );
    } catch (err) {
      feedback.showToast('error', 'Failed to redo action');
    } finally {
      isExecuting.value = false;
    }
  };

  const clear = () => {
    undoStack.value = [];
    redoStack.value = [];
  };

  return {
    undoStack,
    redoStack,
    canUndo,
    canRedo,
    recordAction,
    undo,
    redo,
    clear,
  };
});
