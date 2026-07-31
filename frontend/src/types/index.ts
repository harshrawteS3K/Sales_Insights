/**
 * Shared TypeScript interfaces and types.
 * Centralised from individual component files.
 */

// ─── Auth ─────────────────────────────────────────────────────────────────────
export type UserRole = 'admin' | 'user';

export interface AuthUser {
  role: UserRole;
  name: string;
  title: string;
}

// ─── Layout ───────────────────────────────────────────────────────────────────
export interface LayoutContext {
  userRole: UserRole | null;
  userName: string;
  userTitle: string;
}

// ─── Nav ──────────────────────────────────────────────────────────────────────
export interface NavItem {
  path: string;
  label: string;
  icon: React.ComponentType<{ size?: number; strokeWidth?: number; style?: React.CSSProperties }>;
  exact?: boolean;
  adminOnly?: boolean;
}

export interface QuickLink {
  name: string;
  path: string;
  category: string;
}

// ─── Emails ───────────────────────────────────────────────────────────────────
export interface EmailRecord {
  id: number;
  senderName: string;
  senderEmail: string;
  subject: string;
  dateReceived: string;
  confidenceScore: number;
  outlookWebLink?: string | null;
  graphMessageId?: string | null;
  mailbox?: string | null;
}

// ─── Consolidated Data (report-centric) ───────────────────────────────────────
export interface DistributorInfo {
  name: string;
  company: string;
  address: string;
  phone?: string;
}

/** Transactional sales line (no repeated report metadata). */
export interface SalesLineItem {
  id: number;
  srNo: number;
  customerName: string;
  segment: string;
  product: string;
  quantity: string;
  openingStock?: string | null;
  closingStock?: string | null;
}

/** One imported report with nested sales rows. */
export interface ReportSalesGroup {
  reportId: number;
  distributor: string;
  company?: string | null;
  address?: string | null;
  phone?: string | null;
  reportingMonth?: string | null;
  senderName?: string | null;
  senderEmail?: string | null;
  emailReceivedAt?: string | null;
  mailbox?: string | null;
  importedAt?: string | null;
  confidenceScore?: number | null;
  status?: string | null;
  recordCount: number;
  expectedRows?: number | null;
  importedRows?: number | null;
  incompleteRows?: number | null;
  validationSummary?: {
    total_rows?: number;
    imported_rows?: number;
    skipped_rows?: number;
    warning_count?: number;
    confidence_score?: number | null;
    warnings?: Array<{ reason: string; count: number }>;
    row_errors?: string[];
  } | null;
  validationMessage?: string | null;
  sales: SalesLineItem[];
}

/** @deprecated Prefer ReportSalesGroup — kept for transitional typing */
export interface SalesRecord {
  id: number;
  reportId: number;
  srNo: number;
  distributor: string;
  company?: string;
  customerName: string;
  segment: string;
  product: string;
  openingStock?: string | null;
  closingStock?: string | null;
  quantity: string;
  reportingMonth?: string;
  period?: string;
  importedAt?: string;
  senderName?: string;
  senderEmail?: string;
  emailReceivedAt?: string;
  mailbox?: string;
  graphMessageId?: string;
  internetMessageId?: string;
  confidenceScore?: number;
}

export interface ConsolidatedFilterOptions {
  distributors: string[];
  customers: string[];
  segments: string[];
  products: string[];
  companies: string[];
  reportingMonths: string[];
  periods: string[];
  quarters: string[];
  quantityUnit?: string;
}

export interface QuarterlySummaryRow {
  company: string;
  quarter: string;
  totalQuantity: number;
  totalQuantityDisplay: string;
  unit: string;
  productsSold: number;
  customerCount: number;
  reportsIncluded: number;
  monthsSubmitted: string[];
  monthsExpected: string[];
  isPartial: boolean;
}

export interface QuarterlySummaryResponse {
  success: boolean;
  period: { label: string; kind: string; year?: number | null; months: string[] };
  unit: string;
  totalCompanies: number;
  grandTotalQuantity: number;
  data: QuarterlySummaryRow[];
}

export interface QuarterlyProductRow {
  product: string;
  quantity: number;
  quantityDisplay: string;
  unit: string;
  contributionPct: number;
  customerCount: number;
}

export interface QuarterlyReportResponse {
  success: boolean;
  period: { label: string; kind: string; year?: number | null; months: string[] };
  company: string;
  unit: string;
  totalQuantity: number;
  totalQuantityDisplay: string;
  productsSold: number;
  customerCount: number;
  reportsIncluded: number;
  monthsSubmitted: string[];
  monthsExpected: string[];
  isPartial: boolean;
  products: QuarterlyProductRow[];
}

export interface ConsolidatedRecordsPage {
  success: boolean;
  data: ReportSalesGroup[];
  total: number;
  totalReports?: number;
  skip: number;
  limit: number;
}

export interface ConsolidatedRecordQuery {
  skip?: number;
  limit?: number;
  search?: string;
  distributor?: string;
  customer?: string;
  segment?: string;
  product?: string;
  company?: string;
  period?: string;
  reportingMonth?: string;
  quarter?: string;
  quantity_min?: number | string;
  quantity_max?: number | string;
  imported_from?: string;
  imported_to?: string;
  sort_by?: string;
  sort_dir?: 'asc' | 'desc';
  audit?: boolean;
}

export type SortKey =
  | 'srNo'
  | 'distributor'
  | 'customerName'
  | 'segment'
  | 'product'
  | 'openingStock'
  | 'closingStock'
  | 'quantity'
  | 'reportingMonth'
  | 'period'
  | 'importedAt'
  | 'id';
export type SortDir = 'asc' | 'desc';

// ─── Visualizations ───────────────────────────────────────────────────────────
export interface ProductQty {
  product: string;
  qty: number;
}

export interface DistributorTotal {
  name: string;
  qty: number;
  customers: number;
  products: number;
  avgOrder: number;
}

export interface DistributorProductMix {
  distributor: string;
  'CB 300': number;
  'CB 4600': number;
  'CB 4400': number;
  'CB 548': number;
}

export interface KpiItem {
  label: string;
  value: string;
}

// ─── Audit Trail ──────────────────────────────────────────────────────────────
export type AuditAction =
  | 'Created'
  | 'Updated'
  | 'Deleted'
  | 'Viewed'
  | 'Synced'
  | 'Uploaded'
  | 'Downloaded'
  | 'Processed'
  | 'Login'
  | 'Failed'
  | string;

export interface AuditLog {
  id: string;
  user: string;
  action: AuditAction;
  details: string;
  timestamp: string;
  reportName?: string;
}

// ─── Reports / ExistingReports ────────────────────────────────────────────────
export interface ReportCategories {
  products: string[];
  applications: string[];
}

export interface Report {
  id: string;
  name: string;
  date: string;
  type: string;
  description: string;
  categories: ReportCategories;
  confidenceScore?: number | null;
  expectedRows?: number | null;
  importedRows?: number | null;
  incompleteRows?: number | null;
  validationSummary?: {
    total_rows?: number;
    imported_rows?: number;
    skipped_rows?: number;
    warning_count?: number;
    confidence_score?: number | null;
    warnings?: Array<{ reason: string; count: number }>;
    row_errors?: string[];
  } | null;
  validationMessage?: string | null;
}

export interface ChatMessage {
  id: string;
  type: 'user' | 'assistant';
  content: string;
  timestamp: Date;
}

// ─── Market Research Dashboard ────────────────────────────────────────────────
export interface MarketSizeEntry {
  name: string;
  value: number;
  percent: number;
}

export interface CompetitorEntry {
  name: string;
  share: number;
}

export interface RecentReport {
  name: string;
  country: string;
  segment: string;
  product: string;
  marketSize: string;
  date: string;
}

// ─── Market Research Companion ────────────────────────────────────────────────
export interface ComprehensiveCustomer {
  name: string;
  region: string;
  country: string;
  category: string;
  product: string;
  application: string;
}

export interface CustomerTableData {
  srNo: number;
  customerName: string;
  product: string;
  application: string;
  apcotexSale: number;
  competitorSales: Record<string, number>;
  totalConsumption: number;
  remark: string;
  confidenceScore: number;
  referenceName: string;
  entryPotential: 'High' | 'Medium' | 'Low';
}

export interface CompanyProfile {
  industry: string;
  website: string;
  annualRevenue: string;
  employees: string;
  marketPosition: string;
  keyProducts: string[];
  currentSuppliers: string[];
  growthTrend: string;
  opportunitySummary: string;
}

export type TabKey = 'products' | 'distributors';
