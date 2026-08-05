import { apiRequest } from '../api';
import type { UserRole } from '../types';

export interface LoginResult {
  role: UserRole;
  name: string;
  title: string;
  username: string;
  user_id?: number | null;
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
