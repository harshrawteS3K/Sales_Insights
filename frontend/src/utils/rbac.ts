import type { UserRole } from '../types';

/** Admin-level access (Admin or Super Admin). */
export function isAdminRole(role?: UserRole | string | null): boolean {
  return role === 'admin' || role === 'super_admin';
}

/** Super Admin only (identity management). */
export function isSuperAdminRole(role?: UserRole | string | null): boolean {
  return role === 'super_admin';
}
