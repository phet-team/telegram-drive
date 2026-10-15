<template>
  <div class="fixed top-4 right-4 left-4 sm:left-auto sm:right-5 z-50 flex flex-col gap-2.5 max-w-sm w-auto sm:w-full pointer-events-none select-none">
    <TransitionGroup name="toast">
      <div
        v-for="toast in feedback.toasts"
        :key="toast.id"
        class="pointer-events-auto flex items-start gap-3 p-4 rounded-2xl shadow-[0_4px_20px_rgba(0,0,0,0.12)] border backdrop-blur-md bg-white/95 text-[#1f1f1f] transition-all duration-300"
        :class="{
          'border-green-200': toast.type === 'success',
          'border-red-200': toast.type === 'error',
          'border-blue-200': toast.type === 'info',
        }"
      >
        <!-- Icon -->
        <div class="shrink-0 mt-0.5">
          <CheckCircle2 v-if="toast.type === 'success'" class="w-5 h-5 text-[#0f9d58]" />
          <AlertCircle v-else-if="toast.type === 'error'" class="w-5 h-5 text-[#d93025]" />
          <Info v-else class="w-5 h-5 text-[#0b57d0]" />
        </div>

        <div class="flex-1 text-sm">
          <div v-if="toast.title" class="font-medium text-[#1f1f1f] mb-0.5">
            {{ toast.title }}
          </div>
          <div class="text-[#444746] leading-snug text-[13px]">
            {{ toast.message }}
          </div>
        </div>

        <button
          type="button"
          class="shrink-0 text-[#747775] hover:text-[#1f1f1f] p-1 rounded-full hover:bg-black/5 transition-colors cursor-pointer"
          title="Dismiss"
          @click="feedback.removeToast(toast.id)"
        >
          <X class="w-4 h-4" />
        </button>
      </div>
    </TransitionGroup>
  </div>
</template>

<script setup>
import { CheckCircle2, AlertCircle, Info, X } from 'lucide-vue-next';
import { useFeedbackStore } from '../../stores/feedback';

const feedback = useFeedbackStore();
</script>

<style scoped>
.toast-enter-active,
.toast-leave-active {
  transition: all 0.25s ease;
}
.toast-enter-from {
  opacity: 0;
  transform: translateX(30px) scale(0.95);
}
.toast-leave-to {
  opacity: 0;
  transform: translateX(30px);
}
</style>
