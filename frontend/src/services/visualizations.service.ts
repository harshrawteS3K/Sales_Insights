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

export type TrendPoint = {
  qty: number;
  quarter?: string;
  month?: string;
};

export type HeatmapCell = {
  distributor: string;
  qty: number;
  quarter?: string;
  month?: string;
};

export type HeatmapResponse = {
  months: string[];
  distributors: string[];
  cells: HeatmapCell[];
  quarters?: string[];
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

  getQuarterlyTrend: async (q: VizQuery = {}): Promise<TrendPoint[]> => {
    return apiRequest<TrendPoint[]>('/visualizations/quarterly-trend', {
      params: q,
    });
  },

  /** @deprecated Prefer getQuarterlyTrend */
  getMonthlyTrend: async (q: VizQuery = {}): Promise<TrendPoint[]> => {
    return VisualizationsService.getQuarterlyTrend(q);
  },

  getDistributorQuarterHeatmap: async (q: VizQuery = {}): Promise<HeatmapResponse> => {
    return apiRequest<HeatmapResponse>('/visualizations/distributor-quarter-heatmap', {
      params: q,
    });
  },

  /** @deprecated Prefer getDistributorQuarterHeatmap */
  getDistributorMonthHeatmap: async (q: VizQuery = {}): Promise<HeatmapResponse> => {
    return VisualizationsService.getDistributorQuarterHeatmap(q);
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
