import type { ProductQty, DistributorTotal, DistributorProductMix, KpiItem } from '../types';
import { apiRequest } from '../api';

export type FilterOptions = {
  product?: string[];
  distributor?: string[];
  period: string[];
};

export const VisualizationsService = {
  getProductQuantities: async (period?: string): Promise<ProductQty[]> => {
    return apiRequest<ProductQty[]>('/visualizations/products', { params: { period } });
  },

  getDistributorTotals: async (period?: string): Promise<DistributorTotal[]> => {
    return apiRequest<DistributorTotal[]>('/visualizations/distributors', { params: { period } });
  },

  getProductMix: async (period?: string) => {
    return apiRequest<Array<{ name: string; value: number; color: string }>>(
      '/visualizations/product-mix',
      { params: { period } }
    );
  },

  getProductBarData: async (period?: string) => {
    return apiRequest<Array<{ product: string; qty: number }>>('/visualizations/product-bar', {
      params: { period },
    });
  },

  getDistProductMix: async (period?: string): Promise<DistributorProductMix[]> => {
    return apiRequest<DistributorProductMix[]>('/visualizations/dist-product-mix', {
      params: { period },
    });
  },

  getTop10Distributors: async (period?: string) => {
    return apiRequest<Array<{ name: string; qty: number }>>('/visualizations/top-distributors', {
      params: { period },
    });
  },

  getProductsKpi: async (): Promise<KpiItem[]> => {
    return apiRequest<KpiItem[]>('/visualizations/products-kpi');
  },

  getDistributorsKpi: async (): Promise<KpiItem[]> => {
    return apiRequest<KpiItem[]>('/visualizations/distributors-kpi');
  },

  getProductFilterOptions: async (): Promise<FilterOptions> => {
    return apiRequest<FilterOptions>('/visualizations/product-filter-options');
  },

  getDistributorFilterOptions: async (): Promise<FilterOptions> => {
    return apiRequest<FilterOptions>('/visualizations/distributor-filter-options');
  },
};
