import { apiRequest, getApiBaseUrl } from '../api';
import { getSession } from '../api/session';
import { triggerBrowserDownload } from '../utils/download';

export type SalesInsightsPeriod =
  | 'full_year'
  | 'q1'
  | 'q2'
  | 'q3'
  | 'q4'
  | 'last_3_months'
  | 'last_6_months'
  | 'last_12_months'
  | 'custom';

export type SalesInsightsQuery = {
  distributor_id?: number | null;
  customer?: string | null;
  product?: string | null;
  location?: string | null;
  segment?: string | null;
  fiscal_year_start?: number | null;
  period?: SalesInsightsPeriod | string;
  start_month?: string | null;
  end_month?: string | null;
  search?: string | null;
  page?: number;
  page_size?: number;
};

export type SalesInsightsPayload = {
  kpis: {
    total_sales_mt: number;
    total_sales_mt_display: string;
    total_customers: number;
    total_products: number;
    avg_monthly_sales_mt: number;
    avg_monthly_sales_mt_display: string;
  };
  monthly_trend: Array<{ month: string; qty: number; tooltip?: string }>;
  top_customers: Array<{ customer: string; qty: number }>;
  product_contribution: Array<{ product: string; qty: number }>;
  table: {
    rows: Array<{
      customer: string;
      product: string;
      location?: string;
      month: string;
      qty: number;
      distributor: string;
    }>;
    total: number;
    page: number;
    page_size: number;
  };
  period_months: string[];
};

export type SalesInsightsFilterOptions = {
  distributors: Array<{ id: number; name: string }>;
  customers: string[];
  products: string[];
  locations?: string[];
  segments?: string[];
  financial_years: Array<{ value: number; label: string }>;
  periods: Array<{ value: string; label: string }>;
};

function cleanParams(q: SalesInsightsQuery): Record<string, string | number | boolean | undefined | null> {
  return {
    distributor_id: q.distributor_id || undefined,
    customer: q.customer && q.customer !== 'All' ? q.customer : undefined,
    product: q.product && q.product !== 'All' ? q.product : undefined,
    location: q.location && q.location !== 'All' ? q.location : undefined,
    segment: q.segment && q.segment !== 'All' ? q.segment : undefined,
    fiscal_year_start: q.fiscal_year_start ?? undefined,
    period: q.period || undefined,
    start_month: q.start_month || undefined,
    end_month: q.end_month || undefined,
    search: q.search || undefined,
    page: q.page,
    page_size: q.page_size,
  };
}

export const VisualizationsService = {
  getFilterOptions: async (): Promise<SalesInsightsFilterOptions> => {
    const res = await apiRequest<{ success: boolean; data: SalesInsightsFilterOptions }>(
      '/analytics/filter-options',
    );
    return res.data;
  },

  getSalesInsights: async (q: SalesInsightsQuery = {}): Promise<SalesInsightsPayload> => {
    const res = await apiRequest<{ success: boolean; data: SalesInsightsPayload }>(
      '/analytics/sales-insights',
      { params: cleanParams(q) },
    );
    return res.data;
  },

  exportExcel: async (q: SalesInsightsQuery = {}): Promise<void> => {
    const session = getSession();
    const params = new URLSearchParams();
    const cleaned = cleanParams(q);
    Object.entries(cleaned).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') params.set(k, String(v));
    });
    const url = `${getApiBaseUrl()}/analytics/sales-insights/export?${params.toString()}`;
    const headers: Record<string, string> = {};
    if (session?.name) headers['X-User-Name'] = session.name;
    if (session?.role) headers['X-User-Role'] = session.role;
    if (session?.user_id != null) headers['X-User-Id'] = String(session.user_id);
    if (session?.email) headers['X-User-Email'] = session.email;
    if (session?.segments?.length) headers['X-User-Segments'] = session.segments.join(',');

    const response = await fetch(url, { headers });
    if (!response.ok) {
      throw new Error('Failed to export Sales Insights');
    }
    const blob = await response.blob();
    triggerBrowserDownload(blob, 'sales_insights.xlsx');
  },
};
