import type { AuditTrailPage, AuditTrailRow, AuditTrailQuery } from '../types';
import { apiRequest, getApiBaseUrl } from '../api';
import { getSession } from '../api/session';

export type AuditEventPayload = {
  action: string;
  module: string;
  description: string;
  status?: string;
  entity_type?: string;
  entity_id?: string;
  report_name?: string;
  metadata?: Record<string, unknown>;
};

export const AuditTrailService = {
  /** GET /api/audit-trail — Admin paginated enterprise list */
  list: async (query: AuditTrailQuery = {}): Promise<AuditTrailPage> => {
    return apiRequest<AuditTrailPage>('/audit-trail', {
      params: { ...query } as Record<string, string | number | boolean | undefined | null>,
    });
  },

  /** GET /api/audit-trail/{id} */
  get: async (id: number): Promise<AuditTrailRow> => {
    const res = await apiRequest<{ success: boolean; data: AuditTrailRow }>(`/audit-trail/${id}`);
    return res.data;
  },

  /** POST /api/audit-trail/events — meaningful client events */
  recordEvent: async (payload: AuditEventPayload): Promise<void> => {
    try {
      await apiRequest('/audit-trail/events', { method: 'POST', body: payload });
    } catch {
      // Never block UX on audit failures
    }
  },

  /** GET /api/audit-trail/export — download Excel with current filters */
  exportExcel: async (query: AuditTrailQuery = {}): Promise<void> => {
    const params = new URLSearchParams();
    Object.entries(query).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '' && v !== 'All') {
        params.set(k, String(v));
      }
    });
    const session = getSession();
    const headers: HeadersInit = {};
    if (session) {
      headers['X-User-Role'] = session.role;
      headers['X-User-Name'] = session.name;
    }
    const url = `${getApiBaseUrl()}/audit-trail/export?${params.toString()}`;
    const res = await fetch(url, { headers });
    if (!res.ok) {
      throw new Error('Failed to export audit trail');
    }
    const blob = await res.blob();
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `audit_trail_${new Date().toISOString().slice(0, 10)}.xlsx`;
    a.click();
    URL.revokeObjectURL(a.href);
  },
};
