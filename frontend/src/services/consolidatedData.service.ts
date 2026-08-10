import type {
  SalesRecord,
  DistributorInfo,
  ConsolidatedFilterOptions,
  ConsolidatedRecordsPage,
  ConsolidatedRecordQuery,
  QuarterlySummaryResponse,
  QuarterlyReportResponse,
} from '../types';
import { apiRequest } from '../api';

export interface DeleteResult {
  success: boolean;
  message: string;
  deletedCount: number;
}

export interface DeleteReportPreview {
  distributor: string;
  reportingQuarter?: string;
  reportingMonth?: string;
  period?: string;
  rowCount: number;
}

export const ConsolidatedDataService = {
  /** GET /api/consolidated-data/records */
  getSalesRecords: async (query: ConsolidatedRecordQuery = {}): Promise<ConsolidatedRecordsPage> => {
    return apiRequest<ConsolidatedRecordsPage>('/consolidated-data/records', {
      params: { ...query } as Record<string, string | number | boolean | undefined | null>,
    });
  },

  /** GET /api/consolidated-data/filter-options */
  getFilterOptions: async (): Promise<ConsolidatedFilterOptions> => {
    return apiRequest<ConsolidatedFilterOptions>('/consolidated-data/filter-options');
  },

  /** GET /api/consolidated-data/quarterly/summary */
  getQuarterlySummary: async (params: {
    quarter: string;
    company?: string;
  }): Promise<QuarterlySummaryResponse> => {
    return apiRequest<QuarterlySummaryResponse>('/consolidated-data/quarterly/summary', {
      params,
    });
  },

  /** GET /api/consolidated-data/quarterly/report */
  getQuarterlyReport: async (params: {
    quarter: string;
    company: string;
    page?: number;
    page_size?: number;
    search?: string;
    sort_by?: string;
    sort_order?: 'asc' | 'desc';
  }): Promise<QuarterlyReportResponse> => {
    return apiRequest<QuarterlyReportResponse>('/consolidated-data/quarterly/report', {
      params,
    });
  },

  /** GET /api/consolidated-data/distributors */
  getDistributorDetails: async (): Promise<Record<string, DistributorInfo>> => {
    return apiRequest<Record<string, DistributorInfo>>('/consolidated-data/distributors');
  },

  /** DELETE /api/consolidated-data/{recordId} */
  deleteRecord: async (recordId: number): Promise<DeleteResult> => {
    return apiRequest<DeleteResult>(`/consolidated-data/${recordId}`, { method: 'DELETE' });
  },

  /** GET /api/consolidated-data/report/preview */
  previewDeleteReport: async (
    distributor: string,
    reportingQuarter: string
  ): Promise<DeleteReportPreview> => {
    return apiRequest<DeleteReportPreview>('/consolidated-data/report/preview', {
      params: {
        distributor,
        reportingQuarter,
        reportingMonth: reportingQuarter,
        period: reportingQuarter,
      },
    });
  },

  /** DELETE /api/consolidated-data/report */
  deleteReport: async (distributor: string, reportingQuarter: string): Promise<DeleteResult> => {
    return apiRequest<DeleteResult>('/consolidated-data/report', {
      method: 'DELETE',
      body: {
        distributor,
        reportingQuarter,
        reportingMonth: reportingQuarter,
        period: reportingQuarter,
      },
    });
  },

  /** POST /api/consolidated-data/export-audit */
  auditExport: async (total: number, summary = ''): Promise<void> => {
    await apiRequest('/consolidated-data/export-audit', {
      method: 'POST',
      params: { total, summary },
    });
  },
};

export type { SalesRecord };
