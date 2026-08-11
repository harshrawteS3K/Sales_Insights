import { apiRequest, ApiError } from '../api';
import type {
  Distributor,
  DistributorCreatePayload,
  DistributorListResponse,
  DistributorUpdatePayload,
} from '../types';

export type DistributorListQuery = {
  skip?: number;
  limit?: number;
  search?: string;
  active_only?: boolean;
};

export type EmailDraftResult = {
  success: boolean;
  message: string;
  mailbox: string;
  distributor_id: number;
  distributor_name: string;
  reporting_quarter: string;
  draft_id: string;
  attachment_name: string;
  recipient: string;
  cc?: string | null;
};

export type BulkEmailDraftItemResult = {
  distributor_id: number;
  distributor_name: string;
  success: boolean;
  reason?: string | null;
  draft_id?: string | null;
  attachment_name?: string | null;
  recipient?: string | null;
};

export type BulkEmailDraftJobStart = {
  job_id: string;
  status: string;
  total: number;
  reporting_quarter: string;
};

export type BulkEmailDraftJobStatus = {
  job_id: string;
  status: string;
  reporting_quarter: string;
  total: number;
  processed: number;
  successful: number;
  failed: number;
  results: BulkEmailDraftItemResult[];
  error?: string | null;
};

export const DistributorService = {
  async list(params: DistributorListQuery = {}): Promise<DistributorListResponse> {
    return apiRequest<DistributorListResponse>('/distributors', {
      params: params as Record<string, string | number | boolean | undefined | null>,
    });
  },

  async get(id: number): Promise<Distributor> {
    const res = await apiRequest<{ success: boolean; data: Distributor }>(`/distributors/${id}`);
    return res.data;
  },

  async create(payload: DistributorCreatePayload): Promise<Distributor> {
    const res = await apiRequest<{ success: boolean; data: Distributor }>('/distributors', {
      method: 'POST',
      body: payload,
    });
    return res.data;
  },

  async update(id: number, payload: DistributorUpdatePayload): Promise<Distributor> {
    const res = await apiRequest<{ success: boolean; data: Distributor }>(`/distributors/${id}`, {
      method: 'PUT',
      body: payload,
    });
    return res.data;
  },

  /** Soft-deactivate (DELETE without hard flag). */
  async deactivate(id: number): Promise<void> {
    await apiRequest(`/distributors/${id}`, { method: 'DELETE' });
  },

  async listCustomers(id: number): Promise<string[]> {
    const res = await apiRequest<{ success: boolean; data: string[] }>(
      `/distributors/${id}/customers`,
    );
    return res.data;
  },

  /** Create Microsoft Graph Outlook draft with distributor-specific Excel (not sent). */
  async createEmailDraft(id: number, reporting_quarter: string): Promise<EmailDraftResult> {
    try {
      const res = await apiRequest<{ success: boolean; data: EmailDraftResult; message?: string }>(
        `/distributors/${id}/create-email-draft`,
        {
          method: 'POST',
          body: { reporting_quarter },
        },
      );
      return res.data;
    } catch (err) {
      if (err instanceof ApiError) {
        const lower = err.message.toLowerCase();
        if (lower.includes('email') && (lower.includes('not configured') || lower.includes('missing'))) {
          throw new ApiError('Distributor email address is not configured.', err.status);
        }
        if (lower.includes('graph') || lower.includes('outlook') || err.status >= 500) {
          throw new ApiError(
            'Unable to create the Outlook draft. Please contact the administrator.',
            err.status,
          );
        }
      }
      throw err;
    }
  },

  /** Start sequential bulk Outlook draft job (poll getBulkEmailDraftJob). */
  async startBulkEmailDrafts(
    distributorIds: number[],
    reporting_quarter: string,
  ): Promise<BulkEmailDraftJobStart> {
    const res = await apiRequest<{ success: boolean; data: BulkEmailDraftJobStart }>(
      '/distributors/create-email-drafts-bulk',
      {
        method: 'POST',
        body: { distributor_ids: distributorIds, reporting_quarter },
      },
    );
    return res.data;
  },

  async getBulkEmailDraftJob(jobId: string): Promise<BulkEmailDraftJobStatus> {
    const res = await apiRequest<{ success: boolean; data: BulkEmailDraftJobStatus }>(
      `/distributors/create-email-drafts-bulk/${jobId}`,
    );
    return res.data;
  },
};
