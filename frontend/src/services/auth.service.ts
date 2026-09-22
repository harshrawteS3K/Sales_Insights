import { apiRequest } from '../api';
import type { OutlookSyncPermission, UserRole } from '../types';

export interface LoginResult {
  role: UserRole;
  name: string;
  title: string;
  username: string;
  user_id?: number | null;
  email?: string | null;
  segments?: string[];
  distributor_ids?: number[];
  assigned_distributor_count?: number;
  access_mode?: 'segment' | 'distributor';
  outlook_sync_permission?: OutlookSyncPermission;
}

export const AuthService = {
  async login(username: string, password: string): Promise<LoginResult> {
    const res = await apiRequest<{ success: boolean; data: LoginResult }>('/auth/login', {
      method: 'POST',
      body: { username, password },
    });
    return res.data;
  },
};
