<template>
  <Transition name="fade">
    <div
      v-if="feedback.confirmModal.show"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4 select-none"
    >
      <div
        class="bg-white rounded-[28px] shadow-[0_8px_32px_rgba(0,0,0,0.18)] max-w-md w-full p-6 transform transition-all border border-gray-150 animate-in fade-in zoom-in-95 duration-150"
        @click.stop
      >
        <h3 class="text-2xl font-normal text-[#1f1f1f] mb-3 tracking-tight">
          {{ feedback.confirmModal.title }}
        </h3>
        <p class="text-sm text-[#444746] mb-6 leading-relaxed">
          {{ feedback.confirmModal.message }}
        </p>

        <div class="flex justify-end items-center gap-2">
          <button
            type="button"
            class="px-5 py-2 text-sm font-medium text-[#0b57d0] hover:bg-[#edf2fc] rounded-full transition-colors cursor-pointer"
            @click="handleCancel"
          >
            {{ feedback.confirmModal.cancelText }}
          </button>
          <button
            type="button"
            :class="[
              'px-6 py-2 text-sm font-medium text-white rounded-full shadow-xs transition-all cursor-pointer',
              feedback.confirmModal.isDanger
                ? 'bg-[#d93025] hover:bg-[#b31412]'
                : 'bg-[#0b57d0] hover:bg-[#0842a0]'
            ]"
            @click="handleConfirm"
          >
            {{ feedback.confirmModal.confirmText }}
          </button>
        </div>
      </div>
    </div>
  </Transition>
</template>

<script setup>
import { useFeedbackStore } from '../../stores/feedback';

const feedback = useFeedbackStore();

const handleCancel = () => {
  feedback.closeConfirm();
};

const handleConfirm = () => {
  if (typeof feedback.confirmModal.onConfirm === 'function') {
    feedback.confirmModal.onConfirm();
  }
  feedback.closeConfirm();
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
