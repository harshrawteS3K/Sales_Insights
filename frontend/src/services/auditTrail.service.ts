import type { AuditLog } from '../types';
import { apiRequest } from '../api';

export const AuditTrailService = {
  /** GET /api/audit-trail */
  getAuditLogs: async (): Promise<AuditLog[]> => {
    return apiRequest<AuditLog[]>('/audit-trail');
  },
};
