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
    const res = await apiRequest<{ success: boolean; data: ManagedUser }>(`/users/${id}/username`, {
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

  async setRole(id: number, role: 'admin' | 'user'): Promise<ManagedUser> {
    const res = await apiRequest<{ success: boolean; data: ManagedUser }>(`/users/${id}/role`, {
      method: 'PUT',
      body: { role },
    });
    return res.data;
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

  async listSegmentOptions(): Promise<string[]> {
    const res = await apiRequest<{ success: boolean; data: string[] }>('/users/segments/options');
    return res.data;
  },

  async assignSegments(id: number, segments: string[]): Promise<ManagedUser> {
    const res = await apiRequest<{ success: boolean; data: ManagedUser }>(`/users/${id}/segments`, {
      method: 'PUT',
      body: { segments },
    });
    return res.data;
  },

  async getSegmentMatrix(): Promise<{ segments: string[]; rows: any[] }> {
    const res = await apiRequest<{ success: boolean; data: { segments: string[]; rows: any[] } }>('/users/matrix');
    return res.data;
  },

  async toggleMatrixCell(
    user_id: number,
    segment: string,
    enabled: boolean,
    retain_history?: boolean,
  ): Promise<void> {
    await apiRequest('/users/matrix', {
      method: 'PUT',
      body: {
        user_id,
        segment,
        enabled,
        ...(enabled ? {} : { retain_history: Boolean(retain_history) }),
      },
    });
  },

  async assignDistributors(id: number, distributor_ids: number[]): Promise<ManagedUser> {
    const res = await apiRequest<{ success: boolean; data: ManagedUser }>(`/users/${id}/distributors`, {
      method: 'PUT',
      body: { distributor_ids },
    });
    return res.data;
  },

  async getAccessMode(): Promise<'segment' | 'distributor'> {
    const res = await apiRequest<{ success: boolean; data: { access_mode: string } }>('/users/access-mode');
    const mode = (res.data?.access_mode || 'segment').toLowerCase();
    return mode === 'distributor' ? 'distributor' : 'segment';
  },

  async setAccessMode(access_mode: 'segment' | 'distributor'): Promise<'segment' | 'distributor'> {
    const res = await apiRequest<{ success: boolean; data: { access_mode: string } }>('/users/access-mode', {
      method: 'PUT',
      body: { access_mode },
    });
    const mode = (res.data?.access_mode || access_mode).toLowerCase();
    return mode === 'distributor' ? 'distributor' : 'segment';
  },

  async updateUser(id: number, payload: Partial<{ email: string; full_name: string; title: string; outlook_sync_permission: 'none' | 'own' | 'all' }>): Promise<ManagedUser> {
    const res = await apiRequest<{ success: boolean; data: ManagedUser }>(`/users/${id}`, {
      method: 'PUT',
      body: payload,
    });
    return res.data;
  },

  async setOutlookSyncPermission(
    id: number,
    outlook_sync_permission: 'none' | 'own' | 'all',
  ): Promise<ManagedUser> {
    const res = await apiRequest<{ success: boolean; data: ManagedUser }>(
      `/users/${id}/outlook-sync-permission`,
      {
        method: 'PUT',
        body: { outlook_sync_permission },
      },
    );
    return res.data;
  },

  async resetPassword(id: number): Promise<void> {
    await apiRequest(`/users/${id}/password`, {
      method: 'PUT',
      body: { new_password: 'Sales@123', confirm_password: 'Sales@123' },
    });
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

  async previewBulkPersonaImport(file: File): Promise<any> {
    const formData = new FormData();
    formData.append('file', file);
    const session = getSession();
    const headers: Record<string, string> = {};
    if (session) {
      headers['X-User-Role'] = session.role;
      headers['X-User-Name'] = session.name;
    }
    const response = await fetch(`${getApiBaseUrl()}/personas/bulk-import/preview`, {
      method: 'POST',
      headers,
      body: formData,
    });
    if (!response.ok) {
      const errJson = await response.json().catch(() => ({}));
      throw new ApiError(errJson.detail || errJson.message || 'Preview failed', response.status);
    }
    const json = await response.json();
    return json.data;
  },

  async executeBulkPersonaImport(file: File, replaceExisting: boolean): Promise<any> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('replace_existing', String(replaceExisting));
    const session = getSession();
    const headers: Record<string, string> = {};
    if (session) {
      headers['X-User-Role'] = session.role;
      headers['X-User-Name'] = session.name;
    }
    const response = await fetch(`${getApiBaseUrl()}/personas/bulk-import`, {
      method: 'POST',
      headers,
      body: formData,
    });
    if (!response.ok) {
      const errJson = await response.json().catch(() => ({}));
      throw new ApiError(errJson.detail || errJson.message || 'Import failed', response.status);
    }
    const json = await response.json();
    return json.data;
  },

  async downloadSampleFormat(): Promise<void> {
    const session = getSession();
    const headers: Record<string, string> = {};
    if (session) {
      headers['X-User-Role'] = session.role;
      headers['X-User-Name'] = session.name;
    }
    const url = `${getApiBaseUrl()}/personas/sample-format`;
    const response = await fetch(url, { headers });
    if (!response.ok) {
      throw new ApiError('Sample format download failed', response.status);
    }
    const blob = await response.blob();
    const excelBlob = new Blob([blob], {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    });
    triggerBrowserDownload(excelBlob, 'distributor_employee_mapping_sample.xlsx');
  },
};
