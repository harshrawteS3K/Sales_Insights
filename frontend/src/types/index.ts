/**
 * Shared TypeScript interfaces and types.
 * Centralised from individual component files.
 */

// ─── Auth ─────────────────────────────────────────────────────────────────────
export type UserRole = 'admin' | 'user' | 'super_admin';
export type OutlookSyncPermission = 'none' | 'own' | 'all';

export interface AuthUser {
  role: UserRole;
  name: string;
  title: string;
}

export interface ManagedUser {
  id: number;
  username: string;
  email: string;
  full_name: string;
  title?: string | null;
  role: 'admin' | 'user' | 'super_admin';
  is_active: boolean;
  phone?: string | null;
  department?: string | null;
  segments?: string[];
  distributor_ids?: number[];
  assigned_distributor_count?: number;
  outlook_sync_permission?: OutlookSyncPermission;
  created_at?: string;
  updated_at?: string;
}

export interface UserListResponse {
  success: boolean;
  data: ManagedUser[];
  total: number;
}

export interface UserCreatePayload {
  full_name: string;
  username: string;
  password: string;
  role: 'admin' | 'user';
  is_active: boolean;
  title?: string;
  email?: string;
}

// ─── Layout ───────────────────────────────────────────────────────────────────
export interface LayoutContext {
  userRole: UserRole | null;
  userName: string;
  userTitle: string;
  outlookSyncPermission?: OutlookSyncPermission | null;
}

// ─── Nav ──────────────────────────────────────────────────────────────────────
export interface NavItem {
  path: string;
  label: string;
  icon: React.ComponentType<{ size?: number; strokeWidth?: number; style?: React.CSSProperties }>;
  exact?: boolean;
  adminOnly?: boolean;
  superAdminOnly?: boolean;
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
  processStatus?: string;
  statusLabel?: string;
  attachmentName?: string | null;
  distributorName?: string | null;
  distributor?: string | null;
  location?: string | null;
  segment?: string | null;
  quarter?: string | null;
  subjectValid?: boolean;
  hasExcel?: boolean;
  errorMessage?: string | null;
  /** python = deterministic | llm = OpenAI fallback | manual = user mapping */
  mappingSource?: string | null;
}

// ─── Distributors (admin CRUD) ────────────────────────────────────────────────
export interface Distributor {
  id: number;
  name: string;
  company: string;
  code?: string | null;
  contact_person?: string | null;
  address?: string | null;
  email?: string | null;
  cc_email?: string | null;
  phone?: string | null;
  region?: string | null;
  state?: string | null;
  city?: string | null;
  pincode?: string | null;
  is_active: boolean;
  is_deleted?: boolean;
  notes?: string | null;
  customer_count?: number;
  country?: string;
  created_at?: string;
  updated_at?: string;
}

export interface DistributorListResponse {
  success: boolean;
  data: Distributor[];
  total: number;
}

export interface DistributorCreatePayload {
  name: string;
  company: string;
  code?: string | null;
  contact_person?: string | null;
  email?: string | null;
  cc_email?: string | null;
  is_active?: boolean;
  address?: string | null;
  phone?: string | null;
  region?: string | null;
  state?: string | null;
  city?: string | null;
  pincode?: string | null;
  notes?: string | null;
}

export type DistributorUpdatePayload = Partial<DistributorCreatePayload>;

export type TemplateGenerateMode = 'generic' | 'distributor';

export interface TemplateGeneratePayload {
  mode: TemplateGenerateMode;
  distributor_id?: number;
  reporting_quarter?: string;
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
  segment?: string;
  location?: string;
  product: string;
  quantity: string;
}

/** One imported report with nested sales rows. */
export interface ReportSalesGroup {
  reportId: number;
  distributor: string;
  company?: string | null;
  distributorId?: number | null;
  location?: string | null;
  reportingQuarter?: string | null;
  reportingMonth?: string | null; // backward-compat alias
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
  quantity: string;
  reportingQuarter?: string;
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
  locations?: string[];
  products: string[];
  companies: string[];
  reportingQuarters?: string[];
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

export interface QuarterlyDetailRow {
  srNo: number;
  customer: string;
  segment: string;
  product: string;
  quantity: number;
  quantityDisplay: string;
  unit: string;
  contributionPct: number;
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
  items: QuarterlyDetailRow[];
  totalRecords: number;
  totalPages: number;
  currentPage: number;
  pageSize: number;
  /** @deprecated use items */
  products?: QuarterlyProductRow[];
}

export interface PeriodSummaryItem {
  label: string;
  distributorCount: number;
  reportCount: number;
  totalQuantity: number;
}

export interface ConsolidatedRecordsPage {
  success: boolean;
  data: ReportSalesGroup[];
  total: number;
  totalReports?: number;
  skip: number;
  limit: number;
  pageBy?: 'reports' | 'rows' | string;
  periodSummaries?: PeriodSummaryItem[];
}

export interface ConsolidatedRecordQuery {
  skip?: number;
  limit?: number;
  search?: string;
  distributor?: string;
  customer?: string;
  segment?: string;
  location?: string;
  product?: string;
  company?: string;
  period?: string;
  reportingQuarter?: string;
  reportingMonth?: string;
  quarter?: string;
  quantity_min?: number | string;
  quantity_max?: number | string;
  imported_from?: string;
  imported_to?: string;
  sort_by?: string;
  sort_dir?: 'asc' | 'desc';
  audit?: boolean;
  /** Paginate complete reports (preferred) or sales rows */
  pageBy?: 'reports' | 'rows';
}

export type SortKey =
  | 'srNo'
  | 'distributor'
  | 'customerName'
  | 'segment'
  | 'location'
  | 'product'
  | 'quantity'
  | 'reportingQuarter'
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
  | 'Logout'
  | 'Failed'
  | 'Exported'
  | 'Generated'
  | 'Opened'
  | 'Extract Emails'
  | string;

export type AuditStatus = 'Success' | 'Warning' | 'Failed' | 'Info';

export interface AuditLog {
  id: string;
  user: string;
  action: AuditAction;
  details: string;
  timestamp: string;
  reportName?: string;
  role?: string | null;
  module?: string | null;
  status?: AuditStatus | string | null;
}

export interface AuditTrailRow {
  id: number;
  timestamp: string;
  user: string;
  role?: string | null;
  module?: string | null;
  action: string;
  description: string;
  status: AuditStatus | string;
  entityType?: string | null;
  entityId?: string | null;
  reportName?: string | null;
  ipAddress?: string | null;
  userAgent?: string | null;
  metadata?: Record<string, unknown> | null;
  createdAt?: string | null;
}

export interface AuditTrailPage {
  success: boolean;
  data: AuditTrailRow[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
}

export interface AuditTrailQuery {
  page?: number;
  page_size?: number;
  search?: string;
  role?: string;
  module?: string;
  status?: string;
  action?: string;
  date_from?: string;
  date_to?: string;
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
