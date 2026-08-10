/**
 * Master Data service — Phase 2.
 * Uploads replace active masters; template generate/download use backend APIs.
 */

import { apiRequest, apiUpload, getApiBaseUrl, ApiError } from '../api';
import { getSession } from '../api/session';
import { filenameFromContentDisposition, triggerBrowserDownload } from '../utils/download';
import type { TemplateGeneratePayload } from '../types';

export type CustomerMaster = {
  id: number;
  customer_name: string;
  customer_code?: string | null;
  segment?: string | null;
  region?: string | null;
  country?: string | null;
  city?: string | null;
  address?: string | null;
  is_active: boolean;
};

export type ProductMaster = {
  id: number;
  industry_type: string;
  product_code: string;
  product_name?: string | null;
  segment?: string | null;
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
  status: string;
  message: string;
  records_imported: number;
  duplicates_ignored: number;
  processing_time_ms: number;
  records_upserted?: number;
  records_skipped?: number;
  errors: string[];
  uploaded_at?: string;
  file_name?: string;
  excel_rows?: number;
  blank_customer_name?: number;
  duplicate_names?: number;
  validation_errors?: number;
};

export type TemplateGenerateResult = {
  success: boolean;
  status: string;
  message: string;
  template_version: string;
  file_name: string;
  customers_count: number;
  products_count: number;
  generated_at: string;
  mode?: string;
  warning?: string | null;
  fallback_generic?: boolean;
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

  uploadCustomerMaster: async (
    file: File,
    onProgress?: (p: number) => void,
  ): Promise<MasterUploadResult> => {
    const result = await apiUpload<MasterUploadResult>(
      '/customer-master/upload',
      file,
      'file',
      onProgress,
    );
    return {
      ...result,
      records_imported: result.records_imported ?? result.records_upserted ?? 0,
      uploaded_at: new Date().toISOString(),
      file_name: file.name,
    };
  },

  uploadProductMaster: async (
    file: File,
    onProgress?: (p: number) => void,
  ): Promise<MasterUploadResult> => {
    const result = await apiUpload<MasterUploadResult>(
      '/product-master/upload',
      file,
      'file',
      onProgress,
    );
    return {
      ...result,
      records_imported: result.records_imported ?? result.records_upserted ?? 0,
      uploaded_at: new Date().toISOString(),
      file_name: file.name,
    };
  },

  generateTemplate: async (
    payload: TemplateGeneratePayload = { mode: 'generic' },
  ): Promise<TemplateGenerateResult> => {
    return apiRequest<TemplateGenerateResult>('/template/generate', {
      method: 'POST',
      body: payload,
    });
  },

  downloadTemplate: async (_unused?: string, fileName?: string): Promise<void> => {
    const headers = new Headers();
    const session = getSession();
    if (session) {
      headers.set('X-User-Role', session.role);
      headers.set('X-User-Name', session.name);
    }
    const res = await fetch(`${getApiBaseUrl()}/template/download`, {
      method: 'GET',
      headers,
    });
    if (!res.ok) {
      let message = `Template download failed (${res.status})`;
      try {
        const body = await res.json();
        message = body?.error?.message || body?.message || message;
      } catch {
        // ignore
      }
      throw new ApiError(message, res.status);
    }
    const blob = await res.blob();
    const name = filenameFromContentDisposition(
      res.headers.get('Content-Disposition'),
      fileName || 'Apcotex_Distributor_Template.xlsx',
    );
    // Ensure Excel MIME so the browser treats the blob as a downloadable file.
    const excelBlob =
      blob.type && blob.type !== 'application/octet-stream' && blob.type !== ''
        ? blob
        : new Blob([blob], {
            type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
          });
    triggerBrowserDownload(excelBlob, name);
  },
};
