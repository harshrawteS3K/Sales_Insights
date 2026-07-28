import { apiRequest, apiUpload } from '../api';

export type CustomerMaster = {
  id: number;
  customer_code: string;
  customer_name: string;
  segment: string;
  region?: string | null;
  country?: string | null;
  city?: string | null;
  address?: string | null;
  is_active: boolean;
};

export type ProductMaster = {
  id: number;
  product_code: string;
  product_name: string;
  segment: string;
  description?: string | null;
  unit: string;
  is_active: boolean;
};

type ListResponse<T> = {
  success: boolean;
  data: T[];
  total: number;
};

export type MasterUploadResult = {
  success: boolean;
  message: string;
  records_upserted: number;
  records_skipped: number;
  errors: string[];
};

export const MasterDataService = {
  getCustomers: async (): Promise<CustomerMaster[]> => {
    const res = await apiRequest<ListResponse<CustomerMaster>>('/master-data/customers');
    return res.data;
  },

  getProducts: async (): Promise<ProductMaster[]> => {
    const res = await apiRequest<ListResponse<ProductMaster>>('/master-data/products');
    return res.data;
  },

  uploadCustomers: async (file: File, onProgress?: (p: number) => void) => {
    return apiUpload<MasterUploadResult>('/master-data/customers/upload', file, 'file', onProgress);
  },

  uploadProducts: async (file: File, onProgress?: (p: number) => void) => {
    return apiUpload<MasterUploadResult>('/master-data/products/upload', file, 'file', onProgress);
  },
};
