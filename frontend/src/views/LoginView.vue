<template>
  <div class="h-full w-full overflow-y-auto overscroll-contain flex flex-col items-center justify-start sm:justify-center bg-[#f0f4f9] p-3 sm:p-4 py-6 sm:py-8 select-none font-sans">
    <div class="relative bg-white rounded-[28px] shadow-[0_4px_24px_rgba(0,0,0,0.08)] max-w-md w-full p-5 sm:p-8 border border-gray-150 flex flex-col gap-5 sm:gap-6 my-auto">
      
      <!-- Fullscreen/Card Authentication Loading Overlay -->
      <div
        v-if="isAuthenticating"
        class="absolute inset-0 z-40 bg-white/95 backdrop-blur-xs rounded-[28px] flex flex-col items-center justify-center gap-3.5 p-6 animate-in fade-in duration-200"
      >
        <div class="w-10 h-10 border-3 border-[#0b57d0]/20 border-t-[#0b57d0] rounded-full animate-spin"></div>
        <div class="text-center">
          <p class="text-sm font-semibold text-[#1f1f1f]">{{ authStatusMessage }}</p>
          <p class="text-xs text-[#5f6368] mt-0.5">Please wait while we redirect you...</p>
        </div>
      </div>

      <!-- Header with Google Drive Logo -->
      <div class="flex flex-col items-center text-center">
        <GoogleDriveLogo :size="48" className="mb-3" />
        <h2 class="text-2xl font-normal text-[#1f1f1f] tracking-tight">Sign in</h2>
        <p class="text-sm text-[#444746] mt-1">to continue to Google Drive (Telegram MTProto)</p>
      </div>

      <!-- Email/Password Form -->
      <form @submit.prevent="handleSubmit" class="flex flex-col gap-4">
        <div>
          <label class="block text-xs font-medium text-[#444746] mb-1.5">Email address</label>
          <input
            v-model="email"
            type="email"
            required
            placeholder="name@example.com"
            :class="[
              'w-full px-4 py-3 rounded-xl border text-sm focus:outline-none transition-all text-[#1f1f1f]',
              errorMessage ? 'border-red-400 focus:border-red-500 focus:ring-2 focus:ring-red-500/20' : 'border-gray-300 focus:border-[#0b57d0] focus:ring-2 focus:ring-[#0b57d0]/20'
            ]"
            @input="errorMessage = ''"
          />
        </div>

        <div>
          <label class="block text-xs font-medium text-[#444746] mb-1.5">Password</label>
          <div class="relative">
            <input
              v-model="password"
              :type="showPassword ? 'text' : 'password'"
              required
              placeholder="••••••••"
              :class="[
                'w-full px-4 py-3 rounded-xl border text-sm focus:outline-none transition-all text-[#1f1f1f] pr-10',
                errorMessage ? 'border-red-400 focus:border-red-500 focus:ring-2 focus:ring-red-500/20' : 'border-gray-300 focus:border-[#0b57d0] focus:ring-2 focus:ring-[#0b57d0]/20'
              ]"
              @input="errorMessage = ''"
            />
            <button
              type="button"
              class="absolute right-3 top-1/2 -translate-y-1/2 text-[#747775] hover:text-[#1f1f1f] cursor-pointer p-1"
              :title="showPassword ? 'Hide password' : 'Show password'"
              @click="showPassword = !showPassword"
            >
              <EyeOff v-if="showPassword" class="w-4 h-4" />
              <Eye v-else class="w-4 h-4" />
            </button>
          </div>
          <p v-if="errorMessage" class="text-xs text-red-600 mt-1.5 flex items-center gap-1 font-medium">
            <span>{{ errorMessage }}</span>
          </p>
        </div>

        <button
          type="submit"
          :disabled="auth.loading || isAuthenticating"
          class="w-full py-3 bg-[#0b57d0] hover:bg-[#0842a0] text-white rounded-full font-medium text-sm transition-all shadow-xs disabled:opacity-50 mt-2 cursor-pointer flex items-center justify-center gap-2"
        >
          <div v-if="auth.loading" class="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
          <span>{{ auth.loading ? 'Signing in...' : 'Sign in' }}</span>
        </button>
      </form>

      <!-- Divider -->
      <div class="flex items-center gap-3">
        <div class="h-px bg-gray-200 flex-1"></div>
        <span class="text-xs text-[#747775] uppercase font-medium">or continue with</span>
        <div class="h-px bg-gray-200 flex-1"></div>
      </div>

      <!-- Social / OAuth Logins -->
      <div class="flex flex-col gap-3">
        <!-- Custom Styled Telegram Button -->
        <button
          type="button"
          :disabled="auth.loading || isAuthenticating"
          class="w-full py-2.5 bg-[#24A1DE] hover:bg-[#208fc4] active:bg-[#1a7eae] text-white rounded-full text-xs font-semibold flex items-center justify-center gap-2.5 transition-all shadow-xs cursor-pointer disabled:opacity-50"
          @click="handleTelegramClick"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm4.64 6.8c-.15 1.58-.8 5.42-1.13 7.19-.14.75-.42 1-.68 1.03-.58.05-1.02-.38-1.58-.75-.88-.58-1.38-.94-2.23-1.5-.99-.65-.35-1.01.22-1.59.15-.15 2.71-2.48 2.76-2.69.01-.03.01-.14-.07-.19-.08-.05-.19-.02-.27 0-.12.03-1.99 1.27-5.62 3.72-.53.36-1.01.54-1.44.53-.47-.01-1.38-.27-2.05-.49-.83-.27-1.49-.42-1.43-.88.03-.24.37-.49 1.02-.75 4-1.74 6.68-2.88 8.03-3.44 3.82-1.59 4.62-1.87 5.14-1.88.11 0 .37.03.54.17.14.12.18.28.2.45-.02.07-.02.2-.04.38z"/>
          </svg>
          <span>Sign in with Telegram</span>
        </button>

        <!-- Google Official Button Container / Responsive Wrapper -->
        <div class="w-full flex justify-center items-center min-h-[40px] overflow-hidden relative">
          <!-- Smooth Skeleton Placeholder while GSI renders to prevent flicker -->
          <div
            v-if="!isGoogleReady"
            class="w-full py-2.5 bg-white border border-gray-300 rounded-full text-xs font-semibold flex items-center justify-center gap-2.5 text-[#1f1f1f] shadow-2xs"
          >
            <svg width="18" height="18" viewBox="0 0 24 24">
              <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
              <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
              <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z" fill="#FBBC05"/>
              <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z" fill="#EA4335"/>
            </svg>
            <span>Sign in with Google</span>
          </div>
          <div ref="googleBtnRef" class="w-full flex justify-center" :class="{ 'hidden': !isGoogleReady }"></div>
        </div>
      </div>

      <!-- Footer Link -->
      <div class="text-center text-xs text-[#747775] pt-2 border-t border-gray-100">
        Don't have an account?
        <router-link
          :to="{ path: '/register', query: route.query.redirect ? { redirect: route.query.redirect } : {} }"
          class="text-[#0b57d0] font-semibold hover:underline ml-1"
        >
          Create account
        </router-link>
      </div>
    </div>

    <!-- Localhost Telegram Guidance Modal -->
    <div
      v-if="showLocalhostModal"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4"
    >
      <div class="bg-white rounded-[28px] max-w-md w-full p-6 shadow-2xl border border-gray-150 flex flex-col gap-4 animate-in fade-in duration-150">
        <div class="flex items-center gap-3 text-[#24A1DE]">
          <div class="p-2.5 bg-[#24A1DE]/10 rounded-2xl">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm4.64 6.8c-.15 1.58-.8 5.42-1.13 7.19-.14.75-.42 1-.68 1.03-.58.05-1.02-.38-1.58-.75-.88-.58-1.38-.94-2.23-1.5-.99-.65-.35-1.01.22-1.59.15-.15 2.71-2.48 2.76-2.69.01-.03.01-.14-.07-.19-.08-.05-.19-.02-.27 0-.12.03-1.99 1.27-5.62 3.72-.53.36-1.01.54-1.44.53-.47-.01-1.38-.27-2.05-.49-.83-.27-1.49-.42-1.43-.88.03-.24.37-.49 1.02-.75 4-1.74 6.68-2.88 8.03-3.44 3.82-1.59 4.62-1.87 5.14-1.88.11 0 .37.03.54.17.14.12.18.28.2.45-.02.07-.02.2-.04.38z"/>
            </svg>
          </div>
          <div>
            <h3 class="text-base font-semibold text-[#1f1f1f]">Telegram Login on Localhost</h3>
            <p class="text-xs text-[#5f6368]">การล็อกอินด้วย Telegram บนเครื่อง Local</p>
          </div>
        </div>

        <div class="text-xs text-[#444746] leading-relaxed bg-[#f8fafd] p-3.5 rounded-2xl border border-gray-100 flex flex-col gap-2">
          <p>
            Telegram Login ไม่อนุญาตให้ยืนยันตัวตนบน <b>localhost</b> โดยตรงตามนโยบายความปลอดภัย (ต้องใช้ Domain สาธารณะ + HTTPS ที่ผูกกับ @BotFather)
          </p>
          <p class="text-[11px] text-[#5f6368]">
            สำหรับการทดสอบบนเครื่อง คุณสามารถกด <b>Dev Quick Login</b> เพื่อจำลองเข้าสู่ระบบได้ทันที หรือเปิดหน้าเว็บผ่าน <b>Cloudflare Tunnel</b>
          </p>
        </div>

        <div class="flex flex-col gap-2 pt-1">
          <button
            type="button"
            class="w-full py-2.5 bg-[#0b57d0] hover:bg-[#0842a0] text-white rounded-full text-xs font-medium transition-colors shadow-xs cursor-pointer"
            @click="handleDevMockLogin"
          >
            เข้าสู่ระบบทดสอบ (Dev Quick Login)
          </button>

          <a
            :href="tunnelUrl"
            class="w-full py-2.5 bg-[#f0f4f9] hover:bg-[#e1e9f5] text-[#1f1f1f] rounded-full text-xs font-medium text-center transition-colors cursor-pointer border border-gray-200"
          >
            เปิดผ่าน Cloudflare Tunnel (โดเมนจริง)
          </a>

          <button
            type="button"
            class="w-full py-2 text-[#5f6368] hover:text-[#1f1f1f] text-xs font-medium transition-colors cursor-pointer"
            @click="showLocalhostModal = false"
          >
            ยกเลิก
          </button>
        </div>
      </div>
    </div>

    <!-- Feedback Toasts -->
    <ToastContainer />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { Eye, EyeOff } from 'lucide-vue-next';
import GoogleDriveLogo from '../components/common/GoogleDriveLogo.vue';
import { useAuthStore } from '../stores/auth';
import { useFeedbackStore } from '../stores/feedback';
import ToastContainer from '../components/feedback/ToastContainer.vue';

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const feedback = useFeedbackStore();

const email = ref('');
const password = ref('');
const showPassword = ref(false);
const errorMessage = ref('');

const showLocalhostModal = ref(false);
const isTelegramLoading = ref(false);
const isGoogleLoading = ref(false);
const isGoogleReady = ref(false);
const googleBtnRef = ref(null);
const tunnelUrl = ref('https://patricia-prev-drop-imported.trycloudflare.com/login');

const isAuthenticating = computed(() => {
  return isGoogleLoading.value || isTelegramLoading.value;
});

const authStatusMessage = computed(() => {
  if (isGoogleLoading.value) return 'Signing in with Google...';
  if (isTelegramLoading.value) return 'Signing in with Telegram...';
  return 'Authenticating...';
});

// Centralized navigation that guarantees redirecting to target route
const navigateAfterLogin = () => {
  const target = (route.query.redirect && String(route.query.redirect).startsWith('/'))
    ? String(route.query.redirect)
    : '/';
  window.location.href = target;
};

const handleSubmit = async () => {
  errorMessage.value = '';
  const success = await auth.login(email.value, password.value);
  if (success) {
    navigateAfterLogin();
  } else {
    errorMessage.value = 'Invalid email or password. Please try again.';
  }
};

const loadGoogleScript = () => {
  if (window.google?.accounts?.id) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const existing = document.getElementById('google-gsi-script');
    if (existing) {
      if (window.google?.accounts?.id) {
        resolve();
      } else {
        existing.onload = resolve;
      }
      return;
    }
    const script = document.createElement('script');
    script.id = 'google-gsi-script';
    script.src = 'https://accounts.google.com/gsi/client';
    script.async = true;
    script.defer = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error('Failed to load Google SDK'));
    document.head.appendChild(script);
  });
};

const handleGoogleCredentialResponse = async (response) => {
  if (response && response.credential) {
    isGoogleLoading.value = true;
    try {
      const success = await auth.googleAuth(response.credential);
      if (success) {
        navigateAfterLogin();
      }
    } finally {
      isGoogleLoading.value = false;
    }
  }
};

const setupGoogleAuth = async () => {
  const googleClientId = import.meta.env.VITE_GOOGLE_CLIENT_ID || '';
  if (!googleClientId) return;

  try {
    await loadGoogleScript();
    if (window.google?.accounts?.id) {
      window.google.accounts.id.initialize({
        client_id: googleClientId,
        callback: handleGoogleCredentialResponse,
        auto_select: false,
        cancel_on_tap_outside: true,
      });

      if (googleBtnRef.value) {
        const parentW = googleBtnRef.value.parentElement?.clientWidth || 384;
        const buttonWidth = Math.min(384, Math.max(240, parentW));
        window.google.accounts.id.renderButton(googleBtnRef.value, {
          theme: 'outline',
          size: 'large',
          type: 'standard',
          shape: 'pill',
          text: 'signin_with',
          logo_alignment: 'left',
          width: buttonWidth,
        });
        isGoogleReady.value = true;
      }

      window.google.accounts.id.prompt();
    }
  } catch (err) {
    console.warn('Google GSI initialization error:', err);
  }
};

const loadTelegramScript = () => {
  if (window.Telegram && window.Telegram.Login) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const existing = document.getElementById('telegram-widget-script');
    if (existing) {
      if (window.Telegram && window.Telegram.Login) {
        resolve();
      } else {
        existing.onload = resolve;
      }
      return;
    }
    const script = document.createElement('script');
    script.id = 'telegram-widget-script';
    script.src = 'https://telegram.org/js/telegram-widget.js?22';
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error('Failed to load Telegram SDK'));
    document.head.appendChild(script);
  });
};

const handleTelegramClick = async () => {
  const isLocal = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
  if (isLocal) {
    showLocalhostModal.value = true;
    return;
  }

  isTelegramLoading.value = true;
  try {
    await loadTelegramScript();
    const botId = import.meta.env.VITE_TELEGRAM_BOT_ID || '';
    if (!botId) {
      throw new Error('Telegram Bot ID is not configured.');
    }
    if (!window.Telegram || !window.Telegram.Login || !window.Telegram.Login.auth) {
      throw new Error('Telegram Login API is unavailable');
    }

    window.Telegram.Login.auth({ bot_id: botId, request_access: true }, async (user) => {
      if (user) {
        const success = await auth.telegramAuth(user);
        if (success) {
          navigateAfterLogin();
          return;
        }
      }
      isTelegramLoading.value = false;
    });
  } catch (err) {
    isTelegramLoading.value = false;
    feedback.showToast('error', err.message || 'Cannot open Telegram popup', 'Telegram Error');
  }
};

const handleDevMockLogin = async () => {
  showLocalhostModal.value = false;
  isTelegramLoading.value = true;
  const success = await auth.telegramAuth({ is_dev_mock: true });
  if (success) {
    navigateAfterLogin();
  } else {
    isTelegramLoading.value = false;
  }
};

onMounted(() => {
  // If user already logged in, redirect immediately
  if (auth.isAuthenticated) {
    navigateAfterLogin();
    return;
  }

  // Initialize Google Sign-In button
  setupGoogleAuth();

  // Preload Telegram script in background if not on localhost
  const isLocal = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
  if (!isLocal) {
    loadTelegramScript().catch(() => {});
  }
});
</script>
