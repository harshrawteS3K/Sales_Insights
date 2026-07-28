import type { Report, ReportCategories } from '../types';
import { apiRequest, apiUpload } from '../api';

export type ReportUploadResult = {
  success: boolean;
  message: string;
  records_inserted: number;
  duplicates_skipped: boolean;
};

export const ReportsService = {
  /** GET /api/reports */
  getReports: async (): Promise<Report[]> => {
    return apiRequest<Report[]>('/reports');
  },

  /** GET /api/reports/filter-categories */
  getFilterCategories: async (): Promise<ReportCategories> => {
    return apiRequest<ReportCategories>('/reports/filter-categories');
  },

  /** GET /api/reports/suggested-questions */
  getSuggestedQuestions: async (): Promise<string[]> => {
    return apiRequest<string[]>('/reports/suggested-questions');
  },

  /** POST /api/reports/upload — multipart field `file` (.xlsx / .xlsm) */
  uploadReport: async (
    file: File,
    onProgress?: (percent: number) => void
  ): Promise<ReportUploadResult> => {
    return apiUpload<ReportUploadResult>('/reports/upload', file, 'file', onProgress);
  },
};
