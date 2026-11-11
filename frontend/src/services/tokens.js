import api from './api';

export const listTokens = () => api.get('/auth/tokens/');

export const createToken = ({ name, scopes, folderId = null }) =>
  api.post('/auth/tokens/', { name, scopes, folder_id: folderId });

export const revokeToken = (id) => api.delete(`/auth/tokens/${id}/`);
