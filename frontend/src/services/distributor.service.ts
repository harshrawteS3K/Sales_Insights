import { apiRequest, getApiBaseUrl, ApiError } from '../api';
import { getSession } from '../api/session';
import { filenameFromContentDisposition, triggerBrowserDownload } from '../utils/download';
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

  async generateQuarterlyPackage(id: number, reporting_quarter: string): Promise<void> {
    const session = getSession();
    const headers = new Headers({ 'Content-Type': 'application/json' });
    if (session) {
      headers.set('X-User-Role', session.role);
      headers.set('X-User-Name', session.name);
    }
    const res = await fetch(
      `${getApiBaseUrl()}/distributors/${id}/generate-quarterly-package`,
      {
        method: 'POST',
        headers,
        body: JSON.stringify({ reporting_quarter }),
      },
    );
    if (!res.ok) {
      let message = `Package generation failed (${res.status})`;
      try {
        const body = await res.json();
        message = body?.error?.message || body?.message || body?.detail || message;
        if (typeof message !== 'string') {
          message = `Package generation failed (${res.status})`;
        }
      } catch {
        // ignore
      }
      throw new ApiError(message, res.status);
    }
    const blob = await res.blob();
    const name = filenameFromContentDisposition(
      res.headers.get('Content-Disposition'),
      `distributor_${id}_quarterly_package.zip`,
    );
    const zipBlob =
      blob.type && blob.type !== 'application/octet-stream' && blob.type !== ''
        ? blob
        : new Blob([blob], { type: 'application/zip' });
    triggerBrowserDownload(zipBlob, name);
  },
};
