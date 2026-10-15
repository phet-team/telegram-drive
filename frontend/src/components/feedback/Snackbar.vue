<template>
  <Transition name="snackbar">
    <div
      v-if="feedback.snackbar.show"
      class="fixed bottom-4 left-4 right-4 sm:right-auto sm:left-6 sm:bottom-6 z-50 flex items-center justify-between gap-4 bg-[#303030] text-white px-4 sm:px-5 py-3 rounded-xl shadow-[0_4px_20px_rgba(0,0,0,0.3)] text-sm sm:min-w-[280px] max-w-md border border-white/10 select-none"
    >
      <span class="truncate text-[13.5px]">{{ feedback.snackbar.message }}</span>

      <div class="flex items-center gap-2 shrink-0">
        <button
          v-if="feedback.snackbar.actionText"
          type="button"
          class="text-[#a8c7fa] hover:text-[#d3e3fd] font-medium text-xs tracking-wide transition-colors cursor-pointer px-2 py-1 rounded"
          @click="handleAction"
        >
          {{ feedback.snackbar.actionText }}
        </button>

        <button
          type="button"
          class="text-gray-400 hover:text-white p-1 rounded-full transition-colors cursor-pointer"
          title="Dismiss"
          @click="feedback.closeSnackbar"
        >
          <X class="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  </Transition>
</template>

<script setup>
import { X } from 'lucide-vue-next';
import { useFeedbackStore } from '../../stores/feedback';

const feedback = useFeedbackStore();

const handleAction = async () => {
  const action = feedback.snackbar.onAction;
  feedback.closeSnackbar();
  if (typeof action === 'function') {
    await action();
  }
};
</script>

<style scoped>
.snackbar-enter-active,
.snackbar-leave-active {
  transition: all 0.25s ease-out;
}
.snackbar-enter-from {
  opacity: 0;
  transform: translateY(20px);
}
.snackbar-leave-to {
  opacity: 0;
  transform: translateY(20px);
}
</style>
