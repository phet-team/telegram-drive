<template>
  <div :class="['inline-flex items-center justify-center shrink-0 select-none', sizeClasses]">
    <!-- Folder -->
    <svg v-if="isFolder" :width="pixelSize" :height="pixelSize" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M2.5 5.5C2.5 4.4 3.4 3.5 4.5 3.5H9.5C10.3 3.5 11.1 3.9 11.5 4.6L12.5 6H19.5C20.6 6 21.5 6.9 21.5 8V18.5C21.5 19.6 20.6 20.5 19.5 20.5H4.5C3.4 20.5 2.5 19.6 2.5 18.5V5.5Z" fill="#5f6368"/>
    </svg>

    <!-- PDF Document -->
    <svg v-else-if="isPdf" :width="pixelSize" :height="pixelSize" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M4.5 3C3.67 3 3 3.67 3 4.5V19.5C3 20.33 3.67 21 4.5 21H19.5C20.33 21 21 20.33 21 19.5V8.5L15.5 3H4.5Z" fill="#EA4335"/>
      <path d="M15.5 3V8.5H21L15.5 3Z" fill="#B31412"/>
      <rect x="6" y="12" width="12" height="6" rx="1" fill="white"/>
      <text x="12" y="16.5" font-family="sans-serif" font-size="4.2" font-weight="900" fill="#EA4335" text-anchor="middle">PDF</text>
    </svg>

    <!-- Image -->
    <svg v-else-if="isImage" :width="pixelSize" :height="pixelSize" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M4.5 3C3.67 3 3 3.67 3 4.5V19.5C3 20.33 3.67 21 4.5 21H19.5C20.33 21 21 20.33 21 19.5V8.5L15.5 3H4.5Z" fill="#E24B40"/>
      <path d="M15.5 3V8.5H21L15.5 3Z" fill="#B31412"/>
      <circle cx="9" cy="11.5" r="1.5" fill="white"/>
      <path d="M6 18L10 13.5L13 16.5L15 14.5L18 18H6Z" fill="white"/>
    </svg>

    <!-- Video -->
    <svg v-else-if="isVideo" :width="pixelSize" :height="pixelSize" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M4.5 3C3.67 3 3 3.67 3 4.5V19.5C3 20.33 3.67 21 4.5 21H19.5C20.33 21 21 20.33 21 19.5V8.5L15.5 3H4.5Z" fill="#D93025"/>
      <path d="M15.5 3V8.5H21L15.5 3Z" fill="#A50E0E"/>
      <polygon points="10,11 16,14.5 10,18" fill="white"/>
    </svg>

    <!-- Audio -->
    <svg v-else-if="isAudio" :width="pixelSize" :height="pixelSize" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M4.5 3C3.67 3 3 3.67 3 4.5V19.5C3 20.33 3.67 21 4.5 21H19.5C20.33 21 21 20.33 21 19.5V8.5L15.5 3H4.5Z" fill="#9334E6"/>
      <path d="M15.5 3V8.5H21L15.5 3Z" fill="#681DA8"/>
      <path d="M11 16.5C10.17 16.5 9.5 15.83 9.5 15C9.5 14.17 10.17 13.5 11 13.5C11.35 13.5 11.67 13.62 11.93 13.82L12 11H15V12.5H13.5V15C13.5 15.83 12.83 16.5 12 16.5H11Z" fill="white"/>
    </svg>

    <!-- Spreadsheet / Sheets -->
    <svg v-else-if="isSpreadsheet" :width="pixelSize" :height="pixelSize" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M4.5 3C3.67 3 3 3.67 3 4.5V19.5C3 20.33 3.67 21 4.5 21H19.5C20.33 21 21 20.33 21 19.5V8.5L15.5 3H4.5Z" fill="#0F9D58"/>
      <path d="M15.5 3V8.5H21L15.5 3Z" fill="#0B7542"/>
      <rect x="7" y="11" width="10" height="7" rx="0.5" fill="white"/>
      <line x1="7" y1="13.5" x2="17" y2="13.5" stroke="#0F9D58" stroke-width="0.8"/>
      <line x1="7" y1="15.8" x2="17" y2="15.8" stroke="#0F9D58" stroke-width="0.8"/>
      <line x1="11" y1="11" x2="11" y2="18" stroke="#0F9D58" stroke-width="0.8"/>
    </svg>

    <!-- Presentation / Slides -->
    <svg v-else-if="isPresentation" :width="pixelSize" :height="pixelSize" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M4.5 3C3.67 3 3 3.67 3 4.5V19.5C3 20.33 3.67 21 4.5 21H19.5C20.33 21 21 20.33 21 19.5V8.5L15.5 3H4.5Z" fill="#F4B400"/>
      <path d="M15.5 3V8.5H21L15.5 3Z" fill="#C28B00"/>
      <rect x="7" y="11" width="10" height="7" rx="0.5" fill="white"/>
      <rect x="8.5" y="12.5" width="7" height="4" fill="#F4B400"/>
    </svg>

    <!-- Text / Word Document -->
    <svg v-else-if="isDoc" :width="pixelSize" :height="pixelSize" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M4.5 3C3.67 3 3 3.67 3 4.5V19.5C3 20.33 3.67 21 4.5 21H19.5C20.33 21 21 20.33 21 19.5V8.5L15.5 3H4.5Z" fill="#4285F4"/>
      <path d="M15.5 3V8.5H21L15.5 3Z" fill="#2A66C9"/>
      <line x1="7" y1="12" x2="17" y2="12" stroke="white" stroke-width="1.2" stroke-linecap="round"/>
      <line x1="7" y1="14.5" x2="17" y2="14.5" stroke="white" stroke-width="1.2" stroke-linecap="round"/>
      <line x1="7" y1="17" x2="13" y2="17" stroke="white" stroke-width="1.2" stroke-linecap="round"/>
    </svg>

    <!-- Code File -->
    <svg v-else-if="isCode" :width="pixelSize" :height="pixelSize" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M4.5 3C3.67 3 3 3.67 3 4.5V19.5C3 20.33 3.67 21 4.5 21H19.5C20.33 21 21 20.33 21 19.5V8.5L15.5 3H4.5Z" fill="#00897B"/>
      <path d="M15.5 3V8.5H21L15.5 3Z" fill="#00695C"/>
      <path d="M9.5 12L7.5 14.5L9.5 17" stroke="white" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/>
      <path d="M14.5 12L16.5 14.5L14.5 17" stroke="white" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/>
      <line x1="13" y1="12" x2="11" y2="17" stroke="white" stroke-width="1" stroke-linecap="round"/>
    </svg>

    <!-- Archive / Zip -->
    <svg v-else-if="isArchive" :width="pixelSize" :height="pixelSize" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M4.5 3C3.67 3 3 3.67 3 4.5V19.5C3 20.33 3.67 21 4.5 21H19.5C20.33 21 21 20.33 21 19.5V8.5L15.5 3H4.5Z" fill="#F57C00"/>
      <path d="M15.5 3V8.5H21L15.5 3Z" fill="#CC6500"/>
      <rect x="10.5" y="9" width="3" height="1.5" fill="white"/>
      <rect x="10.5" y="11.5" width="3" height="1.5" fill="white"/>
      <rect x="10.5" y="14" width="3" height="1.5" fill="white"/>
      <rect x="10" y="16.5" width="4" height="2.5" rx="0.5" fill="white"/>
    </svg>

    <!-- Generic Document Fallback -->
    <svg v-else :width="pixelSize" :height="pixelSize" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M4.5 3C3.67 3 3 3.67 3 4.5V19.5C3 20.33 3.67 21 4.5 21H19.5C20.33 21 21 20.33 21 19.5V8.5L15.5 3H4.5Z" fill="#5F6368"/>
      <path d="M15.5 3V8.5H21L15.5 3Z" fill="#3C4043"/>
      <line x1="7" y1="13" x2="17" y2="13" stroke="white" stroke-width="1" stroke-linecap="round"/>
      <line x1="7" y1="16" x2="14" y2="16" stroke="white" stroke-width="1" stroke-linecap="round"/>
    </svg>
  </div>
</template>

<script setup>
import { computed } from 'vue';

const props = defineProps({
  mimeType: {
    type: String,
    default: '',
  },
  isFolder: {
    type: Boolean,
    default: false,
  },
  size: {
    type: String,
    default: 'md', // 'sm' | 'md' | 'lg' | 'xl'
  },
});

const pixelSize = computed(() => {
  switch (props.size) {
    case 'sm':
      return 18;
    case 'lg':
      return 36;
    case 'xl':
      return 48;
    case 'md':
    default:
      return 24;
  }
});

const sizeClasses = computed(() => {
  switch (props.size) {
    case 'sm':
      return 'w-4.5 h-4.5';
    case 'lg':
      return 'w-9 h-9';
    case 'xl':
      return 'w-12 h-12';
    case 'md':
    default:
      return 'w-6 h-6';
  }
});

const isImage = computed(() => props.mimeType?.startsWith('image/'));
const isVideo = computed(() => props.mimeType?.startsWith('video/'));
const isAudio = computed(() => props.mimeType?.startsWith('audio/'));
const isPdf = computed(() => props.mimeType === 'application/pdf');
const isSpreadsheet = computed(() =>
  props.mimeType?.includes('sheet') ||
  props.mimeType?.includes('excel') ||
  props.mimeType === 'text/csv'
);
const isPresentation = computed(() =>
  props.mimeType?.includes('presentation') ||
  props.mimeType?.includes('powerpoint')
);
const isDoc = computed(() =>
  props.mimeType?.includes('document') ||
  props.mimeType?.includes('word') ||
  props.mimeType?.includes('text/plain')
);
const isCode = computed(() =>
  props.mimeType?.includes('javascript') ||
  props.mimeType?.includes('json') ||
  props.mimeType?.includes('python') ||
  props.mimeType?.includes('html') ||
  props.mimeType?.includes('css')
);
const isArchive = computed(() =>
  props.mimeType?.includes('zip') ||
  props.mimeType?.includes('tar') ||
  props.mimeType?.includes('gzip') ||
  props.mimeType?.includes('compressed')
);
</script>
