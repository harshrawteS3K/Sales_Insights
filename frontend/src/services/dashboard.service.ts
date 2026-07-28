import type { KpiItem } from '../types';
import { apiRequest } from '../api';

export type DashboardSummary = {
  total_distributors: number;
  total_reports: number;
  total_sales_records: number;
  total_quantity: number;
  total_emails_processed: number;
  pending_reports: number;
  failed_reports: number;
  last_sync_at: string | null;
  kpis: KpiItem[];
};

type DataResponse<T> = {
  success: boolean;
  data: T;
  message?: string | null;
};

export const DashboardService = {
  /** GET /api/dashboard/summary */
  getSummary: async (): Promise<DashboardSummary> => {
    const res = await apiRequest<DataResponse<DashboardSummary>>('/dashboard/summary');
    return res.data;
  },
};
