import type { EmailRecord } from '../types';
import { apiRequest } from '../api';

export const EmailsService = {
  /** GET /api/emails — processing history */
  getExtractedEmails: async (): Promise<EmailRecord[]> => {
    return apiRequest<EmailRecord[]>('/emails');
  },

  /** POST /api/outlook/sync — Admin only; triggers Graph sync via backend */
  triggerSync: async (): Promise<{ success: boolean; message: string }> => {
    return apiRequest('/outlook/sync', { method: 'POST', body: {} });
  },

  /** DELETE /api/emails/{id} — remove processing history (not Outlook) */
  deleteEmailRecord: async (
    emailId: number
  ): Promise<{ success: boolean; message: string; deletedId: number; outlookDeleted: boolean }> => {
    const res = await apiRequest<{
      success: boolean;
      data: { success: boolean; message: string; deletedId: number; outlookDeleted: boolean };
      message?: string;
    }>(`/emails/${emailId}`, { method: 'DELETE' });
    return res.data ?? (res as unknown as { success: boolean; message: string; deletedId: number; outlookDeleted: boolean });
  },
};
