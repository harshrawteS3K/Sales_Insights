import { apiRequest } from '../api';
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

export type DistributorPerformancePeriod =
  | 'full_year'
  | 'q1'
  | 'q2'
  | 'q3'
  | 'q4'
  | 'last_3_months'
  | 'last_6_months'
  | 'last_12_months'
  | 'custom';

export type DistributorPerformanceQuery = {
  fiscal_year_start?: number | null;
  period?: DistributorPerformancePeriod | string;
  segment?: string | null;
  location?: string | null;
  distributor_id?: number | null;
  customer?: string | null;
  product?: string | null;
  start_month?: string | null;
  end_month?: string | null;
};

export type DistributorPerformanceCustomer = {
  customer: string;
  product_count: number;
  sales_mt: number;
  sales_mt_display: string;
};

export type DistributorPerformanceRow = {
  rank: number;
  distributor_id: number;
  distributor: string;
  location: string;
  customers: number;
  products: number;
  sales_mt: number;
  sales_mt_display: string;
  has_sales: boolean;
  customer_contribution: DistributorPerformanceCustomer[];
};

export type DistributorPerformancePayload = {
  kpis: {
    top_performer: {
      distributor: string;
      distributor_id: number | null;
      sales_mt: number;
      sales_mt_display: string;
    };
    runner_up: {
      distributor: string;
      distributor_id: number | null;
      sales_mt: number;
      sales_mt_display: string;
    };
    active_distributors: {
      submitted: number;
      total: number;
      label: string;
    };
  };
  ranking: DistributorPerformanceRow[];
  filters: {
    fiscal_year_start?: number | null;
    period?: string | null;
    segment?: string | null;
    location?: string | null;
  };
};

export type DistributorPerformanceFilterOptions = {
  financial_years: Array<{ value: number; label: string }>;
  periods: Array<{ value: string; label: string }>;
  segments: string[];
  locations: string[];
  distributors?: Array<{ id: number; name: string }>;
  customers?: string[];
  products?: string[];
};

function cleanPerformanceParams(
  q: DistributorPerformanceQuery,
): Record<string, string | number | boolean | undefined | null> {
  return {
    fiscal_year_start: q.fiscal_year_start ?? undefined,
    period: q.period || undefined,
    segment: q.segment && q.segment !== 'All' ? q.segment : undefined,
    location: q.location && q.location !== 'All' ? q.location : undefined,
    distributor_id: q.distributor_id || undefined,
    customer: q.customer && q.customer !== 'All' ? q.customer : undefined,
    product: q.product && q.product !== 'All' ? q.product : undefined,
    start_month: q.start_month || undefined,
    end_month: q.end_month || undefined,
  };
}

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

  async getPerformanceFilterOptions(): Promise<DistributorPerformanceFilterOptions> {
    const res = await apiRequest<{ success: boolean; data: DistributorPerformanceFilterOptions }>(
      '/distributors/performance/filter-options',
    );
    return res.data;
  },

  async getPerformance(
    q: DistributorPerformanceQuery = {},
  ): Promise<DistributorPerformancePayload> {
    const res = await apiRequest<{ success: boolean; data: DistributorPerformancePayload }>(
      '/distributors/performance',
      { params: cleanPerformanceParams(q) },
    );
    return res.data;
  },
};
