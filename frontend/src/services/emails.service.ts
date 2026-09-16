import type { EmailRecord } from '../types';
import { apiRequest, apiUpload } from '../api';

export type ERPMappingItem = {
  field?: string;
  original?: string | null;
  mapped: string;
  confidence?: number;
  method?: string;
  column?: number | null;
  column_index?: number | null;
};

export type ERPPreviewResponse = {
  sheet_name: string;
  sheet_score?: number;
  header_row?: number;
  confidence: {
    overall: number;
    customer: number;
    product: number;
    quantity: number;
    band: string;
    breakdown?: Record<string, unknown>;
  };
  mapping: ERPMappingItem[];
  column_positions?: Record<string, number | null>;
  rows: Array<{
    customer_name: string;
    product: string;
    sales_quantity: number;
    period?: string | null;
    reporting_quarter?: string | null;
  }>;
  row_count: number;
  candidate_sheets?: string[];
  errors?: string[];
  workbook_name?: string | null;
  email_id?: number | null;
  subject?: string | null;
  sender_email?: string | null;
  sender_name?: string | null;
  distributor_matches?: Array<{
    id: number;
    company: string;
    name?: string | null;
    email?: string | null;
  }>;
  all_distributors?: Array<{
    id: number;
    company: string;
    name?: string | null;
    email?: string | null;
  }>;
  distributor_id?: number | null;
  distributor_unknown?: boolean;
  import_allowed?: boolean;
  available_columns?: Array<{ index: number; header: string; column: number }>;
  monthly_pivot?: boolean;
  fiscal_year_start?: number | null;
  accuracy?: number;
  /** python | llm | manual */
  mapping_source?: string | null;
  attachment_count?: number;
  attachment_names?: string[];
  attachments_capped?: boolean;
};

export type ERPImportResult = {
  report_id: number;
  records_inserted: number;
  duplicate: boolean;
  quality_score: number;
  distributor_id: number;
  reporting_quarter: string;
  workbook_name?: string | null;
  workbooks_imported?: string[];
  workbook_skips?: Array<{ workbook?: string; reason?: string }>;
  reports_created?: number;
  quarters_imported?: string[];
};

export const EmailsService = {
  getExtractedEmails: async (): Promise<EmailRecord[]> => {
    return apiRequest<EmailRecord[]>('/emails');
  },

  triggerSync: async (reporting_quarter?: string): Promise<{ success: boolean; message: string }> => {
    return apiRequest('/outlook/sync', {
      method: 'POST',
      body: {
        max_messages: 5,
        ...(reporting_quarter ? { reporting_quarter } : {}),
      },
    });
  },

  getOutlookOpenLink: async (
    emailId: number,
  ): Promise<{ success: boolean; url: string; available: boolean; message?: string | null }> => {
    return apiRequest(`/emails/${emailId}/outlook-link`);
  },

  deleteEmailRecord: async (
    emailId: number,
  ): Promise<{ success: boolean; message: string; deletedId: number; outlookDeleted: boolean }> => {
    const res = await apiRequest<{
      success: boolean;
      data: { success: boolean; message: string; deletedId: number; outlookDeleted: boolean };
      message?: string;
    }>(`/emails/${emailId}`, { method: 'DELETE' });
    return (
      res.data ??
      (res as unknown as {
        success: boolean;
        message: string;
        deletedId: number;
        outlookDeleted: boolean;
      })
    );
  },

  previewEmail: async (
    emailId: number,
    mapping?: ERPMappingItem[] | Record<string, unknown>,
    fiscalYearStart?: number,
  ): Promise<ERPPreviewResponse> => {
    const res = await apiRequest<{ success: boolean; data: ERPPreviewResponse }>(
      `/erp/emails/${emailId}/preview`,
      {
        method: 'POST',
        body: {
          ...(mapping ? { mapping } : {}),
          ...(fiscalYearStart ? { fiscal_year_start: fiscalYearStart } : {}),
        },
      },
    );
    return res.data;
  },

  importErp: async (payload: {
    email_id: number;
    distributor_id: number;
    reporting_quarter: string;
    fiscal_year_start?: number;
    mapping?: ERPMappingItem[] | Record<string, unknown>;
    rows?: Array<{
      customer_name: string;
      product: string;
      sales_quantity: number;
      period?: string | null;
      reporting_quarter?: string | null;
    }>;
  }): Promise<ERPImportResult> => {
    const res = await apiRequest<{ success: boolean; data: ERPImportResult }>('/erp/import', {
      method: 'POST',
      body: payload,
    });
    return res.data;
  },

  skipEmail: async (emailId: number): Promise<void> => {
    await apiRequest(`/erp/emails/${emailId}/skip`, { method: 'POST' });
  },

  /** Optional file-only preview (multipart). */
  parsePreviewFile: async (file: File): Promise<ERPPreviewResponse> => {
    const res = await apiUpload<{ success: boolean; data: ERPPreviewResponse }>(
      '/erp/parse-preview',
      file,
    );
    return res.data;
  },
};
