/**
 * Market Research APIs are not available in Phase 1 backend.
 * Pages keep working with empty datasets / clear errors — no mock data.
 */

import type {
  MarketSizeEntry,
  CompetitorEntry,
  RecentReport,
  ComprehensiveCustomer,
  CompanyProfile,
} from '../types';

const PHASE1_MESSAGE = 'Market Research APIs are not available in Phase 1.';

async function unavailable<T>(fallback: T): Promise<T> {
  console.warn(PHASE1_MESSAGE);
  return fallback;
}

export const MarketResearchService = {
  getMarketSizeData: async (): Promise<MarketSizeEntry[]> => unavailable([]),
  getCompetitorData: async (): Promise<CompetitorEntry[]> => unavailable([]),
  getRecentReports: async (): Promise<RecentReport[]> => unavailable([]),
  getDashboardKPIs: async (): Promise<Array<{ title: string; value: string }>> => unavailable([]),
  getMockCompetitors: async (): Promise<CompetitorEntry[]> => unavailable([]),
  getMockTopCustomers: async (): Promise<Array<{ name: string; volume: number }>> => unavailable([]),
  getGeography: async (): Promise<Record<string, string[]>> => unavailable({}),
  getCategories: async (): Promise<Record<string, string[]>> => unavailable({}),
  getApplications: async (): Promise<Record<string, string[]>> => unavailable({}),
  getComprehensiveCustomers: async (): Promise<ComprehensiveCustomer[]> => unavailable([]),
  getCompetitors: async (): Promise<string[]> => unavailable([]),
  getRegionCompetitors: async (): Promise<Record<string, string[]>> => unavailable({}),
  getCompanyProfiles: async (): Promise<Record<string, CompanyProfile>> => unavailable({}),
  getReferenceSources: async (): Promise<string[]> => unavailable([]),
  getSupplierLocations: async (): Promise<Record<string, string>> => unavailable({}),
  getPriceTrendData: async (): Promise<Array<{ month: string; price: number }>> => unavailable([]),
};
