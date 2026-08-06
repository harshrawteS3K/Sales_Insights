import { apiRequest, getApiBaseUrl, ApiError } from '../api';
import { getSession } from '../api/session';
import { triggerBrowserDownload } from '../utils/download';
import type { ManagedUser, UserListResponse, UserCreatePayload } from '../types';

export type UserListQuery = {
  skip?: number;
  limit?: number;
  search?: string;
  role?: string;
  status?: string;
};

export const UserManagementService = {
  async list(query: UserListQuery = {}): Promise<UserListResponse> {
    return apiRequest<UserListResponse>('/users', { params: query as Record<string, string | number | boolean | undefined | null> });
  },

  async create(payload: UserCreatePayload): Promise<ManagedUser> {
    const res = await apiRequest<{ success: boolean; data: ManagedUser }>('/users', {
      method: 'POST',
      body: payload,
    });
    return res.data;
  },

  async updateUsername(id: number, username: string): Promise<ManagedUser> {
    const res = await apiRequest<{ success: boolean; data: ManagedUser }>(`/users/${id}`, {
      method: 'PUT',
      body: { username },
    });
    return res.data;
  },

  async changePassword(id: number, new_password: string, confirm_password: string): Promise<void> {
    await apiRequest(`/users/${id}/password`, {
      method: 'PUT',
      body: { new_password, confirm_password },
    });
  },

  async setStatus(id: number, is_active: boolean): Promise<ManagedUser> {
    const res = await apiRequest<{ success: boolean; data: ManagedUser }>(`/users/${id}/status`, {
      method: 'PUT',
      body: { is_active },
    });
    return res.data;
  },

  async remove(id: number): Promise<void> {
    await apiRequest(`/users/${id}`, { method: 'DELETE' });
  },

  async exportExcel(query: UserListQuery = {}): Promise<void> {
    const params = new URLSearchParams();
    if (query.search) params.set('search', query.search);
    if (query.role) params.set('role', query.role);
    if (query.status) params.set('status', query.status);

    const session = getSession();
    const headers: Record<string, string> = {};
    if (session) {
      headers['X-User-Role'] = session.role;
      headers['X-User-Name'] = session.name;
    }
    const url = `${getApiBaseUrl()}/users/export?${params.toString()}`;
    const response = await fetch(url, { headers });
    if (!response.ok) {
      throw new ApiError('Export failed', response.status);
    }
    const blob = await response.blob();
    const excelBlob = new Blob([blob], {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    });
    triggerBrowserDownload(excelBlob, 'users_export.xlsx');
  },
};
