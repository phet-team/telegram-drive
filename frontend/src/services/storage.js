import api from './api';

export const getStorageSettings = () => api.get('/admin/storage/');

export const updateStorageSettings = (payload) => api.put('/admin/storage/', payload);

export const testStorage = () => api.post('/admin/storage/test/');

export const sendTestAlert = () => api.post('/admin/storage/test-alert/');

export const runSelftest = (sizeMb) => api.post('/admin/storage/selftest/', { size_mb: sizeMb });

export const getMyStorage = () => api.get('/storage/me/');

export const updateMyStorage = (payload) => api.put('/storage/me/', payload);

export const testMyStorage = () => api.post('/storage/me/test/');

export const disconnectMyStorage = () => api.post('/storage/me/disconnect/');

export const getAdminUsers = (params) => api.get('/admin/users/', { params });

export const updateAdminUser = (id, payload) => api.patch(`/admin/users/${id}/`, payload);

export const REASON_LABELS = {
  telegram_session_expired: 'The Telegram session expired or was revoked',
  channel_unreachable: 'The storage chat cannot be used',
  telegram_rate_limited: 'Telegram is rate limiting this account',
  telegram_unreachable: 'Telegram cannot be reached from the server',
  credentials_unreadable: 'Stored credentials cannot be decrypted',
  telegram_not_configured: 'Telegram API credentials are missing on the server',
  storage_not_connected: 'The storage account is not connected',
  unexpected_error: 'Unexpected storage error',
};

export const reasonLabel = (reason) => REASON_LABELS[reason] || reason || 'Unknown reason';

// Turns an axios error from the storage endpoints into one readable sentence.
export const errorText = (err, fallback = 'Request failed') => {
  const data = err?.response?.data;
  if (typeof data === 'string' && data) return data;
  if (data?.error && data?.message) return `${data.message} (${data.reason || data.error})`;
  if (data?.error) return data.error;
  if (data?.detail) return data.detail;
  if (data && typeof data === 'object') {
    const first = Object.values(data).flat()[0];
    if (typeof first === 'string') return first;
  }
  return err?.message || fallback;
};
