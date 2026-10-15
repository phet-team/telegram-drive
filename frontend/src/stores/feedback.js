import { defineStore } from 'pinia';
import { ref } from 'vue';

export const useFeedbackStore = defineStore('feedback', () => {
  // Toast notifications
  const toasts = ref([]);
  let nextToastId = 1;

  const showToast = (type, message, title = '', timeout = 4000) => {
    const id = nextToastId++;
    toasts.value.push({ id, type, message, title });
    if (timeout > 0) {
      setTimeout(() => {
        removeToast(id);
      }, timeout);
    }
  };

  const removeToast = (id) => {
    toasts.value = toasts.value.filter(t => t.id !== id);
  };

  // Snackbar with optional Undo action (e.g., bottom left)
  const snackbar = ref({
    show: false,
    message: '',
    actionText: '',
    onAction: null,
  });
  let snackbarTimeout = null;

  const showSnackbar = (message, actionText = '', onAction = null, duration = 6000) => {
    if (snackbarTimeout) clearTimeout(snackbarTimeout);
    snackbar.value = {
      show: true,
      message,
      actionText,
      onAction,
    };
    snackbarTimeout = setTimeout(() => {
      snackbar.value.show = false;
    }, duration);
  };

  const closeSnackbar = () => {
    snackbar.value.show = false;
    if (snackbarTimeout) clearTimeout(snackbarTimeout);
  };

  // Confirm Modal (Replaces browser confirm())
  const confirmModal = ref({
    show: false,
    title: '',
    message: '',
    confirmText: 'Confirm',
    cancelText: 'Cancel',
    isDanger: false,
    onConfirm: null,
  });

  const openConfirm = ({ title, message, confirmText = 'Confirm', cancelText = 'Cancel', isDanger = false, onConfirm }) => {
    confirmModal.value = {
      show: true,
      title,
      message,
      confirmText,
      cancelText,
      isDanger,
      onConfirm,
    };
  };

  const closeConfirm = () => {
    confirmModal.value.show = false;
    confirmModal.value.onConfirm = null;
  };

  return {
    toasts,
    showToast,
    removeToast,
    snackbar,
    showSnackbar,
    closeSnackbar,
    confirmModal,
    openConfirm,
    closeConfirm,
  };
});
