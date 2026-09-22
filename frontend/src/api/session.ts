import type { OutlookSyncPermission, UserRole } from '../types';

const SESSION_KEY = 'apcotex_session';

export interface SessionUser {
  role: UserRole;
  name: string;
  title: string;
  username?: string;
  user_id?: number | null;
  email?: string | null;
  segments?: string[];
  distributor_ids?: number[];
  access_mode?: 'segment' | 'distributor';
  outlook_sync_permission?: OutlookSyncPermission;
}

export function saveSession(user: SessionUser): void {
  sessionStorage.setItem(SESSION_KEY, JSON.stringify(user));
}

export function clearSession(): void {
  sessionStorage.removeItem(SESSION_KEY);
}

export function getSession(): SessionUser | null {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as SessionUser;
  } catch {
    return null;
  }
}
