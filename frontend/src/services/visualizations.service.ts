import type { ProductQty, DistributorTotal, DistributorProductMix, KpiItem } from '../types';
import { apiRequest } from '../api';

export type FilterOptions = {
  product?: string[];
  distributor?: string[];
  period: string[];
};

export type VizQuery = {
  period?: string;
  product?: string;
  distributor?: string;
  top_n?: number;
  limit?: number;
  distributor_limit?: number;
};

export const VisualizationsService = {
  getProductQuantities: async (q: VizQuery = {}): Promise<ProductQty[]> => {
    return apiRequest<ProductQty[]>('/visualizations/products', { params: q });
  },

  getDistributorTotals: async (q: VizQuery = {}): Promise<DistributorTotal[]> => {
    return apiRequest<DistributorTotal[]>('/visualizations/distributors', { params: q });
  },

  getProductMix: async (q: VizQuery = {}) => {
    return apiRequest<Array<{ name: string; value: number; qty?: number; color: string }>>(
      '/visualizations/product-mix',
      { params: q }
    );
  },

  getProductBarData: async (q: VizQuery = {}) => {
    return apiRequest<Array<{ product: string; qty: number }>>('/visualizations/product-bar', {
      params: q,
    });
  },

  getDistProductMix: async (q: VizQuery = {}): Promise<DistributorProductMix[]> => {
    return apiRequest<DistributorProductMix[]>('/visualizations/dist-product-mix', {
      params: q,
    });
  },

  getTop10Distributors: async (q: VizQuery = {}) => {
    return apiRequest<Array<{ name: string; qty: number }>>('/visualizations/top-distributors', {
      params: q,
    });
  },

  getDistributorContribution: async (q: VizQuery = {}) => {
    return apiRequest<Array<{ name: string; value: number; qty: number; color: string }>>(
      '/visualizations/distributor-contribution',
      { params: q }
    );
  },

  getMonthlyTrend: async (q: VizQuery = {}) => {
    return apiRequest<Array<{ month: string; qty: number }>>('/visualizations/monthly-trend', {
      params: q,
    });
  },

  getDistributorMonthHeatmap: async (q: VizQuery = {}) => {
    return apiRequest<{
      months: string[];
      distributors: string[];
      cells: Array<{ distributor: string; month: string; qty: number }>;
    }>('/visualizations/distributor-month-heatmap', { params: q });
  },

  getProductsKpi: async (q: VizQuery = {}): Promise<KpiItem[]> => {
    return apiRequest<KpiItem[]>('/visualizations/products-kpi', { params: q });
  },

  getDistributorsKpi: async (q: VizQuery = {}): Promise<KpiItem[]> => {
    return apiRequest<KpiItem[]>('/visualizations/distributors-kpi', { params: q });
  },

  getProductFilterOptions: async (): Promise<FilterOptions> => {
    return apiRequest<FilterOptions>('/visualizations/product-filter-options');
  },

  getDistributorFilterOptions: async (): Promise<FilterOptions> => {
    return apiRequest<FilterOptions>('/visualizations/distributor-filter-options');
  },
};
