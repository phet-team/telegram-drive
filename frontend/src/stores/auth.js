import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import api, { setAccessToken } from '../services/api';
import { useFeedbackStore } from './feedback';

export const useAuthStore = defineStore('auth', () => {
  const user = ref(null);
  const accessToken = ref('');
  const loading = ref(false);
  const isInitialized = ref(false);

  const isAuthenticated = computed(() => !!accessToken.value);

  const setAuthData = (data) => {
    accessToken.value = data.access;
    setAccessToken(data.access);
    user.value = data.user;
  };

  const clearAuth = () => {
    user.value = null;
    accessToken.value = '';
    setAccessToken(null);
  };

  const initAuth = async () => {
    if (isInitialized.value) return isAuthenticated.value;
    try {
      const { data } = await api.post('/auth/token/refresh/');
      setAuthData(data);
      isInitialized.value = true;
      return true;
    } catch (_) {
      clearAuth();
      isInitialized.value = true;
      return false;
    }
  };

  const fetchMe = async () => {
    if (!accessToken.value) return;
    try {
      const { data } = await api.get('/auth/me/');
      user.value = data;
    } catch (_) {
      clearAuth();
    }
  };

  const login = async (email, password) => {
    loading.value = true;
    const feedback = useFeedbackStore();
    try {
      const { data } = await api.post('/auth/login/', { email, password });
      setAuthData(data);
      feedback.showToast('success', 'Logged in successfully', 'Welcome back');
      return true;
    } catch (err) {
      const msg = err.response?.data?.non_field_errors?.[0] || err.response?.data?.error || 'Login failed';
      feedback.showToast('error', msg, 'Error');
      return false;
    } finally {
      loading.value = false;
    }
  };

  const register = async (email, password, name) => {
    loading.value = true;
    const feedback = useFeedbackStore();
    try {
      const { data } = await api.post('/auth/register/', { email, password, name });
      setAuthData(data);
      feedback.showToast('success', 'Account created successfully', 'Welcome');
      return true;
    } catch (err) {
      const msg = err.response?.data?.email?.[0] || err.response?.data?.password?.[0] || 'Registration failed';
      feedback.showToast('error', msg, 'Error');
      return false;
    } finally {
      loading.value = false;
    }
  };

  const telegramAuth = async (telegramData) => {
    loading.value = true;
    const feedback = useFeedbackStore();
    try {
      const { data } = await api.post('/auth/telegram/', telegramData);
      setAuthData(data);
      feedback.showToast('success', 'Logged in with Telegram', 'Welcome');
      return true;
    } catch (err) {
      const msg = err.response?.data?.error || 'Telegram login failed';
      feedback.showToast('error', msg, 'Error');
      return false;
    } finally {
      loading.value = false;
    }
  };

  const googleAuth = async (idToken) => {
    loading.value = true;
    const feedback = useFeedbackStore();
    try {
      const { data } = await api.post('/auth/google/', { id_token: idToken });
      setAuthData(data);
      feedback.showToast('success', 'Logged in with Google', 'Welcome');
      return true;
    } catch (err) {
      const msg = err.response?.data?.error || 'Google login failed';
      feedback.showToast('error', msg, 'Error');
      return false;
    } finally {
      loading.value = false;
    }
  };

  const logout = async () => {
    try {
      await api.post('/auth/logout/');
    } catch (_) {}
    clearAuth();
    window.location.href = '/login';
  };

  return {
    user,
    accessToken,
    isAuthenticated,
    isInitialized,
    loading,
    initAuth,
    login,
    register,
    telegramAuth,
    googleAuth,
    fetchMe,
    logout,
  };
});
