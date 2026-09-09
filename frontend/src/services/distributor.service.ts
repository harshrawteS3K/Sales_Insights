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

  async delete(id: number): Promise<void> {
    await apiRequest(`/distributors/${id}`, {
      method: 'DELETE',
      params: { hard: true },
    });
  },

  /** @deprecated Use delete() — kept for older callers */
  async deactivate(id: number): Promise<void> {
    await this.delete(id);
  },

  async listCustomers(id: number): Promise<string[]> {
    const res = await apiRequest<{ success: boolean; data: string[] }>(
      `/distributors/${id}/customers`,
    );
    return res.data;
  },
};
