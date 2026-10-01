import { apiRequest } from '../api';

export type ProductMapping = {
  id: number;
  distributor_id: number | null;
  distributor_name: string | null;
  original_product_name: string;
  normalized_product_name: string;
};

export type ProductMappingQuery = {
  distributor?: string;
  original_product?: string;
  normalized_product?: string;
  page?: number;
  page_size?: number;
};

export type ProductMappingPage = {
  success: boolean;
  data: ProductMapping[];
  meta: { page: number; page_size: number; total: number; total_pages: number };
};

export const NormalizationService = {
  /** GET /api/normalization/product-mappings — Super Admin only */
  listProductMappings: async (query: ProductMappingQuery = {}): Promise<ProductMappingPage> => {
    return apiRequest<ProductMappingPage>('/normalization/product-mappings', {
      params: { ...query } as Record<string, string | number | boolean | undefined | null>,
    });
  },
};
