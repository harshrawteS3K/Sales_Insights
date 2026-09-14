import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useNavigate } from 'react-router';
import {
  Search,
  Download,
  Filter,
  ChevronUp,
  ChevronDown,
  Eye,
  Trash2,
  FileX,
  X,
  ChevronLeft,
  ChevronRight,
  ArrowRight,
  CalendarDays,
  Building2,
  Pencil,
  Check,
} from 'lucide-react';
import { BLUE, BORDER, TEAL } from '../../constants/theme';
import type {
  ReportSalesGroup,
  SalesLineItem,
  SortKey,
  ConsolidatedFilterOptions,
  ConsolidatedRecordQuery,
} from '../../types';
import { ConsolidatedDataService } from '../../services/consolidatedData.service';
import { DistributorService } from '../../services/distributor.service';
import { ApiError, getSession } from '../../api';
import { isAdminRole } from '../../utils/rbac';
import { StatusBanner } from '../../components/common/StatusBanner';
import { DataQualityWarning } from '../../components/ui/DataQualityWarning';
import { SearchAutocomplete } from '../../components/ui/SearchAutocomplete';
import {
  applyPeriodSummaries,
  buildYearQuarterTimeline,
  formatMt,
  overviewFromPeriodSummaries,
} from '../../utils/quarter';
import type { PeriodSummaryItem } from '../../types';

type FilterState = {
  distributor: string;
  customer: string;
  product: string;
  company: string;
  reportingQuarter: string;
  quarter: string;
  quantityMin: string;
  quantityMax: string;
  importedFrom: string;
  importedTo: string;
};

const EMPTY_FILTERS: FilterState = {
  distributor: '',
  customer: '',
  product: '',
  company: '',
  reportingQuarter: '',
  quarter: '',
  quantityMin: '',
  quantityMax: '',
  importedFrom: '',
  importedTo: '',
};

/** Reports per page — complete distributor reports (not mid-cut sales rows). */
const PAGE_SIZE = 20;
const EXPAND_ALL_THRESHOLD = 3;

type ViewTarget = { report: ReportSalesGroup; line: SalesLineItem };
type DeleteRecordTarget = { report: ReportSalesGroup; line: SalesLineItem };

function reportingQuarterOf(report: ReportSalesGroup): string {
  return (report.reportingQuarter || report.reportingMonth)?.trim() || '—';
}

/** Primary business entity label for reporting. */
function companyOf(report: ReportSalesGroup): string {
  return (report.company || report.distributor || '').trim() || '—';
}

function formatConfidence(score?: number | null): string {
  if (score == null || Number.isNaN(score)) return '—';
  const pct = score <= 1 ? score * 100 : score;
  return `${Math.round(pct)}%`;
}

function csvEscape(value: string | number | null | undefined): string {
  const s = value == null ? '' : String(value);
  return `"${s.replace(/"/g, '""')}"`;
}

export function ConsolidatedData() {
  const navigate = useNavigate();
  const isAdmin = isAdminRole(getSession()?.role);

  const [searchInput, setSearchInput] = useState('');
  const [search, setSearch] = useState('');
  const [filters, setFilters] = useState<FilterState>(EMPTY_FILTERS);
  const [appliedFilters, setAppliedFilters] = useState<FilterState>(EMPTY_FILTERS);
  const [showFilters, setShowFilters] = useState(false);

  const [sortKey, setSortKey] = useState<SortKey>('id');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc');
  const [page, setPage] = useState(0);

  const [loaded, setLoaded] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reportGroups, setReportGroups] = useState<ReportSalesGroup[]>([]);
  const [total, setTotal] = useState(0);
  const [totalReports, setTotalReports] = useState(0);
  const [periodSummaries, setPeriodSummaries] = useState<PeriodSummaryItem[]>([]);
  const [filterOptions, setFilterOptions] = useState<ConsolidatedFilterOptions>({
    distributors: [],
    customers: [],
    segments: [],
    products: [],
    companies: [],
    reportingQuarters: [],
    reportingMonths: [],
    periods: [],
    quarters: [],
  });

  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set());
  const [expandedQuarters, setExpandedQuarters] = useState<Set<string>>(new Set());
  const [viewTarget, setViewTarget] = useState<ViewTarget | null>(null);
  const [deleteRecordTarget, setDeleteRecordTarget] = useState<DeleteRecordTarget | null>(null);
  const [deleteReportTarget, setDeleteReportTarget] = useState<ReportSalesGroup | null>(null);
  const [deleteReportCount, setDeleteReportCount] = useState<number | null>(null);
  const [actionBusy, setActionBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [editingDistributorId, setEditingDistributorId] = useState<number | null>(null);
  const [editDistributorName, setEditDistributorName] = useState('');
  const [renameBusy, setRenameBusy] = useState(false);

  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pendingAudit = useRef(false);

  const reportingQuarterOptions = useMemo(
    () =>
      filterOptions.reportingQuarters?.length
        ? filterOptions.reportingQuarters
        : filterOptions.reportingMonths?.length
          ? filterOptions.reportingMonths
          : filterOptions.periods || [],
    [filterOptions]
  );

  const activeFilterCount = useMemo(() => {
    return Object.values(appliedFilters).filter(v => v !== '').length + (search ? 1 : 0);
  }, [appliedFilters, search]);

  const buildQuery = useCallback(
    (opts?: { skip?: number; audit?: boolean; limit?: number }): ConsolidatedRecordQuery => {
      const f = appliedFilters;
      const quarter = f.reportingQuarter || f.quarter || undefined;
      return {
        skip: opts?.skip ?? page * PAGE_SIZE,
        limit: opts?.limit ?? PAGE_SIZE,
        search: search || undefined,
        distributor: f.distributor || undefined,
        customer: f.customer || undefined,
        product: f.product || undefined,
        company: f.company || undefined,
        reportingQuarter: quarter,
        reportingMonth: quarter,
        period: quarter,
        quarter: quarter,
        quantity_min: f.quantityMin || undefined,
        quantity_max: f.quantityMax || undefined,
        imported_from: f.importedFrom || undefined,
        imported_to: f.importedTo || undefined,
        sort_by: sortKey,
        sort_dir: sortDir,
        audit: opts?.audit,
        pageBy: 'reports',
      };
    },
    [appliedFilters, page, search, sortKey, sortDir]
  );

  const syncExpanded = useCallback((groups: ReportSalesGroup[]) => {
    if (groups.length === 0) {
      setExpandedIds(new Set());
      setExpandedQuarters(new Set());
      return;
    }
    const built = buildYearQuarterTimeline(groups);
    const newestQuarter = built[0]?.quarters[0]?.label;
    setExpandedQuarters(newestQuarter ? new Set([newestQuarter]) : new Set());
    if (groups.length <= EXPAND_ALL_THRESHOLD) {
      setExpandedIds(new Set(groups.map(g => g.reportId)));
      return;
    }
    setExpandedIds(new Set());
  }, []);

  const timeline = useMemo(() => {
    const built = buildYearQuarterTimeline(reportGroups);
    return applyPeriodSummaries(built, periodSummaries);
  }, [reportGroups, periodSummaries]);

  const quarterOverview = useMemo(() => {
    if (periodSummaries.length) return overviewFromPeriodSummaries(periodSummaries);
    return timeline.flatMap(y => y.quarters);
  }, [periodSummaries, timeline]);

  const toggleQuarter = (label: string) => {
    setExpandedQuarters(prev => {
      const next = new Set(prev);
      if (next.has(label)) next.delete(label);
      else next.add(label);
      return next;
    });
  };

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const audit = pendingAudit.current;
      pendingAudit.current = false;
      const query = buildQuery({ audit });
      const [pageResult, options] = await Promise.all([
        ConsolidatedDataService.getSalesRecords(query),
        ConsolidatedDataService.getFilterOptions(),
      ]);
      setReportGroups(pageResult.data);
      setTotal(pageResult.total);
      setTotalReports(pageResult.totalReports ?? pageResult.data.length);
      setPeriodSummaries(pageResult.periodSummaries || []);
      setFilterOptions(options);
      syncExpanded(pageResult.data);
      setLoaded(true);
    } catch (err) {
      setLoaded(false);
      setError(err instanceof ApiError ? err.message : 'Failed to load sales data');
    } finally {
      setLoading(false);
    }
  }, [buildQuery, syncExpanded]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  useEffect(() => {
    if (searchTimer.current) clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(() => {
      setPage(0);
      setSearch(searchInput.trim());
    }, 350);
    return () => {
      if (searchTimer.current) clearTimeout(searchTimer.current);
    };
  }, [searchInput]);

  const handleSort = (key: SortKey) => {
    if (sortKey === key) setSortDir(d => (d === 'asc' ? 'desc' : 'asc'));
    else {
      setSortKey(key);
      setSortDir('asc');
    }
    setPage(0);
  };

  const applyFilters = () => {
    pendingAudit.current = true;
    setAppliedFilters({ ...filters });
    setPage(0);
    setShowFilters(false);
  };

  const resetFilters = () => {
    setFilters(EMPTY_FILTERS);
    setAppliedFilters(EMPTY_FILTERS);
    setSearchInput('');
    setSearch('');
    setPage(0);
  };

  const toggleExpanded = (reportId: number) => {
    setExpandedIds(prev => {
      const next = new Set(prev);
      if (next.has(reportId)) next.delete(reportId);
      else next.add(reportId);
      return next;
    });
  };

  const startRenameDistributor = (report: ReportSalesGroup, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!report.distributorId || !isAdmin) return;
    setEditingDistributorId(report.distributorId);
    setEditDistributorName(companyOf(report));
  };

  const saveDistributorName = async (report: ReportSalesGroup) => {
    if (!report.distributorId || !editDistributorName.trim()) {
      setEditingDistributorId(null);
      return;
    }
    setRenameBusy(true);
    setActionError(null);
    try {
      const updated = await DistributorService.update(report.distributorId, {
        company: editDistributorName.trim(),
        name: editDistributorName.trim(),
      });
      const label = updated.company || updated.name;
      setReportGroups(prev =>
        prev.map(g =>
          g.distributorId === report.distributorId
            ? { ...g, company: label, distributor: updated.name || label }
            : g,
        ),
      );
      setEditingDistributorId(null);
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Failed to rename distributor');
    } finally {
      setRenameBusy(false);
    }
  };

  const exportExcel = async () => {
    try {
      const all = await ConsolidatedDataService.getSalesRecords({
        ...buildQuery({
          skip: 0,
          limit: Math.min(Math.max(totalReports || total, 1), 5000),
        }),
      });
      const csvRows: string[] = [];
      let exportedLines = 0;

      all.data.forEach(report => {
        const quarter = reportingQuarterOf(report);
        const detailLines = [
          report.distributor,
          report.company || '',
          `Reporting Quarter: ${quarter}`,
        ].filter(Boolean);

        csvRows.push(csvEscape(detailLines.join('\n')));
        csvRows.push(
          ['Sr No', 'Customer', 'Product', 'Quantity'].map(csvEscape).join(',')
        );

        report.sales.forEach(line => {
          exportedLines += 1;
          csvRows.push(
            [line.srNo, line.customerName, line.product, line.quantity]
              .map(csvEscape)
              .join(',')
          );
        });

        csvRows.push('');
      });

      const blob = new Blob([csvRows.join('\n')], { type: 'text/csv;charset=utf-8;' });
      const link = document.createElement('a');
      const url = URL.createObjectURL(blob);
      link.setAttribute('href', url);
      link.setAttribute(
        'download',
        `Consolidated_Quarterly_Report_${new Date().toISOString().split('T')[0]}.csv`
      );
      link.style.visibility = 'hidden';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      await ConsolidatedDataService.auditExport(
        exportedLines,
        activeFilterCount ? ' (filtered)' : ''
      );
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Export failed');
    }
  };

  const openDeleteReport = async (report: ReportSalesGroup) => {
    setActionError(null);
    setDeleteReportTarget(report);
    setDeleteReportCount(null);
    const quarter = (report.reportingQuarter || report.reportingMonth)?.trim();
    if (!quarter) {
      setActionError('Reporting quarter is missing for this report.');
      setDeleteReportCount(0);
      return;
    }
    try {
      const preview = await ConsolidatedDataService.previewDeleteReport(
        report.company || report.distributor,
        quarter
      );
      setDeleteReportCount(preview.rowCount);
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Failed to preview delete');
    }
  };

  const confirmDeleteRecord = async () => {
    if (!deleteRecordTarget) return;
    setActionBusy(true);
    setActionError(null);
    try {
      await ConsolidatedDataService.deleteRecord(deleteRecordTarget.line.id);
      setDeleteRecordTarget(null);
      await loadData();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Delete failed');
    } finally {
      setActionBusy(false);
    }
  };

  const confirmDeleteReport = async () => {
    if (!deleteReportTarget) return;
    const quarter = (deleteReportTarget.reportingQuarter || deleteReportTarget.reportingMonth)?.trim();
    if (!quarter) {
      setActionError('Reporting quarter is missing for this report.');
      return;
    }
    setActionBusy(true);
    setActionError(null);
    try {
      await ConsolidatedDataService.deleteReport(
        deleteReportTarget.company || deleteReportTarget.distributor,
        quarter
      );
      setDeleteReportTarget(null);
      setDeleteReportCount(null);
      await loadData();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Delete report failed');
    } finally {
      setActionBusy(false);
    }
  };

  const SortIcon = ({ col }: { col: SortKey }) => {
    if (sortKey !== col) return <ChevronUp size={11} style={{ opacity: 0.25 }} />;
    return sortDir === 'asc' ? <ChevronUp size={11} color={BLUE} /> : <ChevronDown size={11} color={BLUE} />;
  };

  const totalPages = Math.max(1, Math.ceil((totalReports || 0) / PAGE_SIZE));
  const pageSalesCount = useMemo(
    () => reportGroups.reduce((sum, g) => sum + (g.sales?.length || 0), 0),
    [reportGroups]
  );

  const selectStyle: React.CSSProperties = {
    width: '100%',
    height: 36,
    padding: '0 10px',
    border: `1px solid ${BORDER}`,
    borderRadius: 7,
    fontSize: '0.8125rem',
    color: '#374151',
    background: 'white',
    fontFamily: 'inherit',
  };

  const labelStyle: React.CSSProperties = {
    display: 'block',
    fontSize: '0.6875rem',
    fontWeight: 700,
    color: '#6B7280',
    textTransform: 'uppercase',
    letterSpacing: '0.04em',
    marginBottom: 6,
  };

  return (
    <div style={{ padding: '28px 32px', fontFamily: "'Inter', system-ui, sans-serif" }}>
      <div style={{ marginBottom: 20 }}>
        <h1 style={{ fontSize: '1.375rem', fontWeight: 700, color: '#111827', margin: 0, marginBottom: 4 }}>
          Consolidated Sales Data
        </h1>
        <p style={{ fontSize: '0.875rem', color: '#6B7280', margin: 0 }}>
          Master repository of distributor company sales — ACTIVE quarterly reports
        </p>
      </div>

      <StatusBanner loading={loading} error={error} onRetry={() => loadData()} loadingText="Loading sales data…" />

      {loaded && (
        <>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16, flexWrap: 'wrap' }}>
            <div style={{ position: 'relative', flex: '1 1 280px', maxWidth: 420 }}>
              <Search
                size={14}
                style={{
                  position: 'absolute',
                  left: 10,
                  top: '50%',
                  transform: 'translateY(-50%)',
                  color: '#9CA3AF',
                }}
              />
              <input
                value={searchInput}
                onChange={e => setSearchInput(e.target.value)}
                placeholder="Search distributor, company, customer, product, reporting quarter…"
                style={{
                  width: '100%',
                  height: 36,
                  paddingLeft: 32,
                  paddingRight: 12,
                  border: `1px solid ${BORDER}`,
                  borderRadius: 7,
                  fontSize: '0.8125rem',
                  color: '#374151',
                  background: 'white',
                  outline: 'none',
                  fontFamily: 'inherit',
                }}
              />
            </div>

            <button
              type="button"
              onClick={() => setShowFilters(true)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                padding: '0 14px',
                height: 36,
                background: activeFilterCount ? 'rgba(31,95,168,0.08)' : 'white',
                border: `1px solid ${activeFilterCount ? BLUE : BORDER}`,
                borderRadius: 7,
                fontSize: '0.8125rem',
                fontWeight: 500,
                color: activeFilterCount ? BLUE : '#374151',
                cursor: 'pointer',
              }}
            >
              <Filter size={13} />
              Filters
              {activeFilterCount > 0 && (
                <span
                  style={{
                    minWidth: 18,
                    height: 18,
                    borderRadius: 9,
                    background: BLUE,
                    color: 'white',
                    fontSize: '0.6875rem',
                    fontWeight: 700,
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    padding: '0 5px',
                  }}
                >
                  {activeFilterCount}
                </span>
              )}
            </button>

            {activeFilterCount > 0 && (
              <button
                type="button"
                onClick={resetFilters}
                style={{
                  height: 36,
                  padding: '0 12px',
                  background: 'white',
                  border: `1px solid ${BORDER}`,
                  borderRadius: 7,
                  fontSize: '0.8125rem',
                  color: '#6B7280',
                  cursor: 'pointer',
                }}
              >
                Reset
              </button>
            )}

            <div style={{ marginLeft: 'auto' }}>
              <button
                type="button"
                onClick={exportExcel}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                  padding: '0 18px',
                  height: 36,
                  background: BLUE,
                  border: 'none',
                  borderRadius: 7,
                  fontSize: '0.8125rem',
                  fontWeight: 600,
                  color: 'white',
                  cursor: 'pointer',
                }}
              >
                <Download size={13} />
                Export Excel
              </button>
            </div>
          </div>

          {reportGroups.length === 0 ? (
            <div
              style={{
                background: 'white',
                border: `1px solid ${BORDER}`,
                borderRadius: 12,
                padding: '48px 24px',
                textAlign: 'center',
                color: '#9CA3AF',
                fontSize: '0.875rem',
              }}
            >
              No quarterly reports available
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {quarterOverview.length > 0 && (
                <div
                  style={{
                    background: 'white',
                    border: `1px solid ${BORDER}`,
                    borderRadius: 12,
                    padding: '16px 18px',
                    marginBottom: 8,
                  }}
                >
                  <div
                    style={{
                      fontSize: '0.75rem',
                      fontWeight: 700,
                      color: '#6B7280',
                      textTransform: 'uppercase',
                      letterSpacing: '0.05em',
                      marginBottom: 10,
                    }}
                  >
                    Quarterly Overview
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    {quarterOverview.map(q => (
                      <div
                        key={`ov-${q.label}`}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: 16,
                          flexWrap: 'wrap',
                          fontSize: '0.8125rem',
                          color: '#374151',
                          padding: '6px 0',
                          borderBottom: `1px solid ${BORDER}`,
                        }}
                      >
                        <span style={{ fontWeight: 700, minWidth: 88, color: '#111827' }}>
                          {q.label}
                          {q.range ? (
                            <span style={{ fontWeight: 500, color: '#9CA3AF' }}> ({q.range})</span>
                          ) : null}
                        </span>
                        <span style={{ color: '#6B7280' }}>
                          {q.distributorCount} distributor{q.distributorCount === 1 ? '' : 's'}
                        </span>
                        <span style={{ marginLeft: 'auto', fontWeight: 700, color: BLUE }}>
                          {formatMt(q.totalQuantity)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {timeline.map(yearBucket => (
                <div key={`year-${yearBucket.year}`} style={{ marginBottom: 8 }}>
                  <div
                    style={{
                      position: 'sticky',
                      top: 0,
                      zIndex: 10,
                      background: 'white',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 16,
                      padding: '16px 0',
                      borderBottom: `1px solid ${BORDER}`,
                    }}
                  >
                    <div style={{ height: 1, flex: 1, background: '#D1D5DB' }} />
                    <div
                      style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: 8,
                        padding: '8px 16px',
                        borderRadius: 999,
                        background: 'rgba(31,95,168,0.06)',
                        border: '1px solid rgba(31,95,168,0.22)',
                      }}
                    >
                      <CalendarDays size={18} color={BLUE} />
                      <span style={{ fontSize: '1.0625rem', fontWeight: 700, color: '#111827' }}>
                        {yearBucket.year || 'Unknown'}
                      </span>
                    </div>
                    <div style={{ height: 1, flex: 1, background: '#D1D5DB' }} />
                    <span style={{ fontSize: '0.75rem', color: '#6B7280', whiteSpace: 'nowrap' }}>
                      {yearBucket.reportCount} quarterly report
                      {yearBucket.reportCount === 1 ? '' : 's'}
                    </span>
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: 12, paddingTop: 14 }}>
                    {yearBucket.quarters.map(qBucket => {
                      const qOpen = expandedQuarters.has(qBucket.label);
                      return (
                        <div
                          key={qBucket.label}
                          style={{
                            borderRadius: 12,
                            border: `1px solid ${BORDER}`,
                            background: '#F9FAFB',
                            boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
                            overflow: 'hidden',
                          }}
                        >
                          <button
                            type="button"
                            onClick={() => toggleQuarter(qBucket.label)}
                            style={{
                              width: '100%',
                              display: 'flex',
                              alignItems: 'center',
                              gap: 12,
                              padding: '14px 16px',
                              border: 'none',
                              background: qOpen ? '#F3F4F6' : 'transparent',
                              cursor: 'pointer',
                              textAlign: 'left',
                              fontFamily: 'inherit',
                            }}
                          >
                            <span
                              style={{
                                display: 'inline-flex',
                                transform: qOpen ? 'rotate(90deg)' : 'rotate(0deg)',
                                transition: 'transform 0.15s',
                                color: BLUE,
                              }}
                            >
                              <ChevronRight size={16} />
                            </span>
                            <div style={{ flex: 1, minWidth: 0 }}>
                              <div style={{ fontSize: '0.9375rem', fontWeight: 700, color: '#111827' }}>
                                {qBucket.label}
                                {qBucket.range ? (
                                  <span style={{ fontWeight: 500, color: '#6B7280' }}>
                                    {' '}
                                    ({qBucket.range})
                                  </span>
                                ) : null}
                              </div>
                              <div style={{ marginTop: 2, fontSize: '0.75rem', color: '#6B7280' }}>
                                {qBucket.distributorCount} distributor
                                {qBucket.distributorCount === 1 ? '' : 's'}
                                {' · '}
                                {formatMt(qBucket.totalQuantity)}
                                {typeof qBucket.reportCountFull === 'number' &&
                                  qBucket.reports.length < qBucket.reportCountFull && (
                                    <span style={{ color: '#9CA3AF' }}>
                                      {' '}
                                      · showing {qBucket.reports.length} of {qBucket.reportCountFull} on
                                      this page
                                    </span>
                                  )}
                              </div>
                            </div>
                          </button>

                          {qOpen && (
                            <div
                              style={{
                                display: 'flex',
                                flexDirection: 'column',
                                gap: 10,
                                padding: '0 12px 12px',
                              }}
                            >
                              {qBucket.reports.map(report => {
                                const expanded = expandedIds.has(report.reportId);
                                const quarter = reportingQuarterOf(report);
                                return (
                  <div
                    key={report.reportId}
                    style={{
                      background: 'white',
                      border: `1px solid ${BORDER}`,
                      borderRadius: 12,
                      boxShadow: '0 1px 4px rgba(0,0,0,0.04)',
                      overflow: 'hidden',
                    }}
                  >
                    {/* Accordion header */}
                    <button
                      type="button"
                      onClick={() => toggleExpanded(report.reportId)}
                      style={{
                        width: '100%',
                        display: 'flex',
                        alignItems: 'center',
                        gap: 12,
                        padding: '14px 18px',
                        background: expanded ? '#F8FAFC' : 'white',
                        border: 'none',
                        borderBottom: expanded ? `1px solid ${BORDER}` : 'none',
                        cursor: 'pointer',
                        textAlign: 'left',
                        fontFamily: 'inherit',
                      }}
                    >
                      <span
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          width: 28,
                          height: 28,
                          borderRadius: 8,
                          background: 'rgba(31,95,168,0.08)',
                          color: BLUE,
                          flexShrink: 0,
                        }}
                      >
                        <Building2 size={15} />
                      </span>
                      <span
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          width: 24,
                          height: 24,
                          borderRadius: 6,
                          background: 'rgba(31,95,168,0.08)',
                          color: BLUE,
                          flexShrink: 0,
                          transition: 'transform 0.15s',
                          transform: expanded ? 'rotate(90deg)' : 'rotate(0deg)',
                        }}
                      >
                        <ChevronRight size={14} />
                      </span>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div
                          style={{
                            fontSize: '0.9375rem',
                            fontWeight: 700,
                            color: '#111827',
                            lineHeight: 1.35,
                            display: 'flex',
                            alignItems: 'center',
                            gap: 8,
                          }}
                        >
                          {isAdmin &&
                          report.distributorId &&
                          editingDistributorId === report.distributorId ? (
                            <>
                              <input
                                value={editDistributorName}
                                onClick={e => e.stopPropagation()}
                                onChange={e => setEditDistributorName(e.target.value)}
                                onKeyDown={e => {
                                  if (e.key === 'Enter') {
                                    e.preventDefault();
                                    void saveDistributorName(report);
                                  }
                                  if (e.key === 'Escape') setEditingDistributorId(null);
                                }}
                                style={{
                                  flex: 1,
                                  minWidth: 160,
                                  padding: '6px 10px',
                                  border: `1px solid ${BORDER}`,
                                  borderRadius: 8,
                                  fontSize: '0.875rem',
                                  fontWeight: 600,
                                }}
                                autoFocus
                              />
                              <button
                                type="button"
                                title="Save"
                                disabled={renameBusy}
                                onClick={e => {
                                  e.stopPropagation();
                                  void saveDistributorName(report);
                                }}
                                style={{
                                  ...actionBtn,
                                  background: TEAL,
                                  color: 'white',
                                  border: 'none',
                                }}
                              >
                                <Check size={13} />
                              </button>
                              <button
                                type="button"
                                title="Cancel"
                                onClick={e => {
                                  e.stopPropagation();
                                  setEditingDistributorId(null);
                                }}
                                style={actionBtn}
                              >
                                <X size={13} />
                              </button>
                            </>
                          ) : (
                            <>
                              <span>{companyOf(report)}</span>
                              {isAdmin && report.distributorId ? (
                                <button
                                  type="button"
                                  title="Edit distributor name"
                                  onClick={e => startRenameDistributor(report, e)}
                                  style={{
                                    border: 'none',
                                    background: 'transparent',
                                    color: '#6B7280',
                                    cursor: 'pointer',
                                    padding: 2,
                                    display: 'inline-flex',
                                  }}
                                >
                                  <Pencil size={14} />
                                </button>
                              ) : null}
                            </>
                          )}
                        </div>
                        <div
                          style={{
                            marginTop: 3,
                            fontSize: '0.75rem',
                            color: '#6B7280',
                            display: 'flex',
                            flexWrap: 'wrap',
                            gap: '4px 14px',
                          }}
                        >
                          {report.importedAt && <span>Imported: {report.importedAt}</span>}
                          {(report.senderEmail || report.senderName) && (
                            <span>
                              Sender: {report.senderEmail || report.senderName}
                            </span>
                          )}
                          <span>Confidence: {formatConfidence(report.confidenceScore)}</span>
                          <span>
                            {report.recordCount} sales line{report.recordCount === 1 ? '' : 's'}
                          </span>
                        </div>
                      </div>
                      <button
                        type="button"
                        title="View details"
                        onClick={e => {
                          e.stopPropagation();
                          toggleExpanded(report.reportId);
                        }}
                        style={actionBtn}
                      >
                        <Eye size={13} />
                        View
                      </button>
                      {isAdmin && (
                        <button
                          type="button"
                          title="Delete Report"
                          onClick={e => {
                            e.stopPropagation();
                            openDeleteReport(report);
                          }}
                          style={actionBtnReport}
                        >
                          <FileX size={13} />
                          Delete Report
                        </button>
                      )}
                    </button>

                    {expanded && (
                      <div>
                        {/* Report Information */}
                        <div
                          style={{
                            padding: '16px 18px',
                            background: '#FAFBFC',
                            borderBottom: `1px solid ${BORDER}`,
                          }}
                        >
                          <div
                            style={{
                              fontSize: '0.6875rem',
                              fontWeight: 700,
                              color: '#6B7280',
                              textTransform: 'uppercase',
                              letterSpacing: '0.05em',
                              marginBottom: 12,
                            }}
                          >
                            Report Information
                          </div>
                          <div
                            style={{
                              display: 'grid',
                              gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))',
                              gap: '12px 20px',
                            }}
                          >
                            <InfoCell label="Distributor Company" value={companyOf(report)} />
                            {report.distributor && report.company && report.distributor !== report.company && (
                              <InfoCell label="Representative" value={report.distributor} />
                            )}
                            <InfoCell label="Company" value={report.company || '—'} />
                            <InfoCell label="Reporting Quarter" value={quarter} />
                            <InfoCell
                              label="Sender"
                              value={
                                report.senderName
                                  ? `${report.senderName}${report.senderEmail ? ` (${report.senderEmail})` : ''}`
                                  : report.senderEmail || '—'
                              }
                            />
                            <InfoCell label="Imported On" value={report.importedAt || report.emailReceivedAt || '—'} />
                            <InfoCell label="Confidence" value={formatConfidence(report.confidenceScore)} />
                          </div>
                          <DataQualityWarning
                            variant="full"
                            confidenceScore={report.confidenceScore}
                            incompleteRows={report.incompleteRows}
                            importedRows={report.importedRows}
                            expectedRows={report.expectedRows}
                            validationSummary={report.validationSummary}
                            validationMessage={report.validationMessage}
                          />
                        </div>

                        {/* Nested sales table */}
                        <div style={{ overflowX: 'auto' }}>
                          <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 780 }}>
                            <thead>
                              <tr style={{ background: '#F3F4F6', borderBottom: `1px solid ${BORDER}` }}>
                                <th onClick={() => handleSort('srNo')} style={thStyle('left')}>
                                  <div style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                                    Sr No <SortIcon col="srNo" />
                                  </div>
                                </th>
                                <th onClick={() => handleSort('customerName')} style={thStyle('left')}>
                                  <div style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                                    Customer <SortIcon col="customerName" />
                                  </div>
                                </th>
                                <th onClick={() => handleSort('product')} style={thStyle('left')}>
                                  <div style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                                    Product <SortIcon col="product" />
                                  </div>
                                </th>
                                <th onClick={() => handleSort('quantity')} style={thStyle('right')}>
                                  <div style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                                    Quantity <SortIcon col="quantity" />
                                  </div>
                                </th>
                                <th style={{ ...thStyle('left'), cursor: 'default' }}>Actions</th>
                              </tr>
                            </thead>
                            <tbody>
                              {report.sales.map((line, idx) => (
                                <tr
                                  key={line.id}
                                  style={{
                                    borderBottom:
                                      idx < report.sales.length - 1 ? `1px solid ${BORDER}` : 'none',
                                    background: idx % 2 === 0 ? 'white' : '#FAFAFA',
                                  }}
                                >
                                  <td style={tdMuted}>{line.srNo}</td>
                                  <td
                                    style={{
                                      padding: '12px 16px',
                                      fontSize: '0.875rem',
                                      fontWeight: 600,
                                      color: '#111827',
                                      whiteSpace: 'nowrap',
                                    }}
                                  >
                                    {line.customerName}
                                  </td>
                                  <td style={{ padding: '12px 16px' }}>
                                    <span style={chipBlue}>{line.product}</span>
                                  </td>
                                  <td
                                    style={{
                                      padding: '12px 16px',
                                      fontSize: '0.875rem',
                                      fontWeight: 700,
                                      color: '#111827',
                                      textAlign: 'right',
                                    }}
                                  >
                                    {line.quantity}
                                  </td>
                                  <td style={{ padding: '10px 12px', whiteSpace: 'nowrap' }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                                      <button
                                        type="button"
                                        title="View"
                                        onClick={() => setViewTarget({ report, line })}
                                        style={actionBtn}
                                      >
                                        <Eye size={13} />
                                        View
                                      </button>
                                      {isAdmin && (
                                        <button
                                          type="button"
                                          title="Delete Record"
                                          onClick={() => {
                                            setActionError(null);
                                            setDeleteRecordTarget({ report, line });
                                          }}
                                          style={actionBtnDanger}
                                        >
                                          <Trash2 size={13} />
                                          Delete Record
                                        </button>
                                      )}
                                    </div>
                                  </td>
                                </tr>
                              ))}
                              {report.sales.length === 0 && (
                                <tr>
                                  <td
                                    colSpan={6}
                                    style={{
                                      padding: '28px',
                                      textAlign: 'center',
                                      color: '#9CA3AF',
                                      fontSize: '0.8125rem',
                                    }}
                                  >
                                    No sales lines in this report for the current filters.
                                  </td>
                                </tr>
                              )}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    )}
                  </div>
                                );
                              })}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Pagination */}
          <div
            style={{
              marginTop: 14,
              padding: '10px 20px',
              border: `1px solid ${BORDER}`,
              borderRadius: 10,
              background: '#F9FAFB',
              fontSize: '0.8125rem',
              color: '#6B7280',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 12,
              flexWrap: 'wrap',
            }}
          >
            <span>
              Showing{' '}
              {reportGroups.length === 0
                ? 0
                : `${page * PAGE_SIZE + 1}–${page * PAGE_SIZE + reportGroups.length}`}{' '}
              of {totalReports} distributor report{totalReports === 1 ? '' : 's'}
              <span style={{ color: '#9CA3AF' }}>
                {' '}
                · {pageSalesCount.toLocaleString()} sales rows on this page · {total.toLocaleString()}{' '}
                total
              </span>
            </span>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <button
                type="button"
                disabled={page <= 0}
                onClick={() => setPage(p => Math.max(0, p - 1))}
                style={pagerBtn(page <= 0)}
              >
                <ChevronLeft size={14} />
              </button>
              <span>
                Page {page + 1} / {totalPages}
              </span>
              <button
                type="button"
                disabled={page + 1 >= totalPages}
                onClick={() => setPage(p => p + 1)}
                style={pagerBtn(page + 1 >= totalPages)}
              >
                <ChevronRight size={14} />
              </button>
            </div>
          </div>

          {/* Proceed to Visualizations */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 16,
              marginTop: 20,
              flexWrap: 'wrap',
            }}
          >
            <p style={{ margin: 0, fontSize: '0.8125rem', color: '#6B7280' }}>
              {total > 0
                ? `Charts and KPIs will use the ${total} consolidated sales record${total === 1 ? '' : 's'} currently in the database.`
                : 'Import sales records before opening visualizations.'}
            </p>
            <button
              type="button"
              disabled={total <= 0}
              onClick={() => navigate('/visualizations')}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 10,
                padding: '13px 28px',
                background: total > 0 ? BLUE : '#9CA3AF',
                color: 'white',
                border: 'none',
                borderRadius: 10,
                fontSize: '0.9375rem',
                fontWeight: 700,
                cursor: total > 0 ? 'pointer' : 'not-allowed',
                boxShadow: total > 0 ? '0 4px 14px rgba(31,95,168,0.25)' : 'none',
                transition: 'background 0.15s, transform 0.15s',
                opacity: total > 0 ? 1 : 0.7,
              }}
              onMouseEnter={e => {
                if (total <= 0) return;
                e.currentTarget.style.background = '#1a4f8e';
                e.currentTarget.style.transform = 'translateY(-1px)';
              }}
              onMouseLeave={e => {
                if (total <= 0) return;
                e.currentTarget.style.background = BLUE;
                e.currentTarget.style.transform = 'translateY(0)';
              }}
            >
              Proceed to Visualization <ArrowRight size={17} />
            </button>
          </div>
        </>
      )}

      {/* Filter Drawer */}
      {showFilters && (
        <div style={overlayStyle} onClick={() => setShowFilters(false)}>
          <div
            style={{
              position: 'absolute',
              top: 0,
              right: 0,
              width: 'min(420px, 100%)',
              height: '100%',
              background: 'white',
              boxShadow: '-4px 0 24px rgba(0,0,0,0.12)',
              display: 'flex',
              flexDirection: 'column',
            }}
            onClick={e => e.stopPropagation()}
          >
            <div
              style={{
                padding: '18px 20px',
                borderBottom: `1px solid ${BORDER}`,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}
            >
              <h2 style={{ margin: 0, fontSize: '1.0625rem', fontWeight: 700, color: '#111827' }}>Filters</h2>
              <button type="button" onClick={() => setShowFilters(false)} style={iconCloseBtn}>
                <X size={16} />
              </button>
            </div>
            <div style={{ padding: 20, overflowY: 'auto', flex: 1, display: 'flex', flexDirection: 'column', gap: 14 }}>
              <SearchAutocomplete
                label="Distributor Company"
                options={filterOptions.companies?.length ? filterOptions.companies : filterOptions.distributors}
                value={filters.company || filters.distributor || 'All'}
                allValue="All"
                onChange={v =>
                  setFilters(f => ({
                    ...f,
                    company: v === 'All' ? '' : v,
                    distributor: '',
                  }))
                }
                placeholder="Search company…"
                width="100%"
              />
              <FilterSelect
                label="Customer"
                value={filters.customer}
                options={filterOptions.customers}
                onChange={v => setFilters(f => ({ ...f, customer: v }))}
                selectStyle={selectStyle}
                labelStyle={labelStyle}
              />
              <SearchAutocomplete
                label="Product"
                options={filterOptions.products}
                value={filters.product || 'All'}
                allValue="All"
                onChange={v => setFilters(f => ({ ...f, product: v === 'All' ? '' : v }))}
                placeholder="Search product…"
                width="100%"
              />
              <FilterSelect
                label="Company"
                value={filters.company}
                options={filterOptions.companies}
                onChange={v => setFilters(f => ({ ...f, company: v }))}
                selectStyle={selectStyle}
                labelStyle={labelStyle}
              />
              <FilterSelect
                label="Reporting Quarter"
                value={filters.reportingQuarter}
                options={reportingQuarterOptions}
                onChange={v => setFilters(f => ({ ...f, reportingQuarter: v, quarter: v }))}
                selectStyle={selectStyle}
                labelStyle={labelStyle}
              />
              <div>
                <label style={labelStyle}>Quantity Range</label>
                <div style={{ display: 'flex', gap: 8 }}>
                  <input
                    type="number"
                    placeholder="Min"
                    value={filters.quantityMin}
                    onChange={e => setFilters(f => ({ ...f, quantityMin: e.target.value }))}
                    style={selectStyle}
                  />
                  <input
                    type="number"
                    placeholder="Max"
                    value={filters.quantityMax}
                    onChange={e => setFilters(f => ({ ...f, quantityMax: e.target.value }))}
                    style={selectStyle}
                  />
                </div>
              </div>
              <div>
                <label style={labelStyle}>Imported Date</label>
                <div style={{ display: 'flex', gap: 8 }}>
                  <input
                    type="date"
                    value={filters.importedFrom}
                    onChange={e => setFilters(f => ({ ...f, importedFrom: e.target.value }))}
                    style={selectStyle}
                  />
                  <input
                    type="date"
                    value={filters.importedTo}
                    onChange={e => setFilters(f => ({ ...f, importedTo: e.target.value }))}
                    style={selectStyle}
                  />
                </div>
              </div>
            </div>
            <div style={{ padding: 16, borderTop: `1px solid ${BORDER}`, display: 'flex', gap: 10 }}>
              <button
                type="button"
                onClick={() => {
                  setFilters(EMPTY_FILTERS);
                }}
                style={{
                  flex: 1,
                  height: 40,
                  borderRadius: 8,
                  border: `1px solid ${BORDER}`,
                  background: 'white',
                  fontWeight: 600,
                  fontSize: '0.8125rem',
                  color: '#374151',
                  cursor: 'pointer',
                }}
              >
                Reset Filters
              </button>
              <button
                type="button"
                onClick={applyFilters}
                style={{
                  flex: 1,
                  height: 40,
                  borderRadius: 8,
                  border: 'none',
                  background: BLUE,
                  fontWeight: 600,
                  fontSize: '0.8125rem',
                  color: 'white',
                  cursor: 'pointer',
                }}
              >
                Apply Filters
              </button>
            </div>
          </div>
        </div>
      )}

      {/* View Modal */}
      {viewTarget && (
        <Modal onClose={() => setViewTarget(null)} title="Sales Line Detail">
          <div
            style={{
              marginBottom: 16,
              padding: '12px 14px',
              background: '#F8FAFC',
              border: `1px solid ${BORDER}`,
              borderRadius: 8,
            }}
          >
            <div
              style={{
                fontSize: '0.6875rem',
                fontWeight: 700,
                color: '#6B7280',
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
                marginBottom: 10,
              }}
            >
              Report Context
            </div>
          <DetailRow label="Distributor Company" value={companyOf(viewTarget.report)} />
            <DetailRow
              label="Representative"
              value={
                viewTarget.report.distributor &&
                viewTarget.report.distributor !== viewTarget.report.company
                  ? viewTarget.report.distributor
                  : '—'
              }
            />
            <DetailRow label="Reporting Quarter" value={reportingQuarterOf(viewTarget.report)} />
            <DetailRow
              label="Sender"
              value={
                viewTarget.report.senderName
                  ? `${viewTarget.report.senderName}${viewTarget.report.senderEmail ? ` · ${viewTarget.report.senderEmail}` : ''}`
                  : viewTarget.report.senderEmail || '—'
              }
            />
            <DetailRow label="Imported On" value={viewTarget.report.importedAt || '—'} />
            <DetailRow label="Confidence" value={formatConfidence(viewTarget.report.confidenceScore)} />
          </div>
          <div
            style={{
              fontSize: '0.6875rem',
              fontWeight: 700,
              color: '#6B7280',
              textTransform: 'uppercase',
              letterSpacing: '0.05em',
              marginBottom: 10,
            }}
          >
            Sales Line
          </div>
          <DetailRow label="Sr No" value={String(viewTarget.line.srNo)} />
          <DetailRow label="Customer" value={viewTarget.line.customerName} />
          <DetailRow label="Product" value={viewTarget.line.product} />
          <DetailRow label="Quantity" value={viewTarget.line.quantity} />
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 20 }}>
            <button type="button" onClick={() => setViewTarget(null)} style={modalSecondaryBtn}>
              Close
            </button>
          </div>
        </Modal>
      )}

      {/* Delete Record Modal */}
      {deleteRecordTarget && (
        <Modal onClose={() => !actionBusy && setDeleteRecordTarget(null)} title="Delete Sales Record">
          <p style={{ margin: '0 0 12px', fontSize: '0.875rem', color: '#374151', lineHeight: 1.55 }}>
            You are about to permanently delete this sales record.
          </p>
          <p style={{ margin: '0 0 8px', fontSize: '0.8125rem', color: '#6B7280' }}>
            <strong style={{ color: '#111827' }}>{deleteRecordTarget.line.customerName}</strong>
            {' · '}
            {deleteRecordTarget.report.distributor}
            {' · '}
            {reportingQuarterOf(deleteRecordTarget.report)}
          </p>
          <p style={{ margin: '0 0 16px', fontSize: '0.8125rem', color: '#DC2626', fontWeight: 500 }}>
            This action cannot be undone.
          </p>
          {actionError && <p style={{ color: '#DC2626', fontSize: '0.8125rem' }}>{actionError}</p>}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 8 }}>
            <button
              type="button"
              disabled={actionBusy}
              onClick={() => setDeleteRecordTarget(null)}
              style={modalSecondaryBtn}
            >
              Cancel
            </button>
            <button type="button" disabled={actionBusy} onClick={confirmDeleteRecord} style={modalDangerBtn}>
              {actionBusy ? 'Deleting…' : 'Delete'}
            </button>
          </div>
        </Modal>
      )}

      {/* Delete Report Modal */}
      {deleteReportTarget && (
        <Modal onClose={() => !actionBusy && setDeleteReportTarget(null)} title="Delete Imported Report">
          <p style={{ margin: '0 0 12px', fontSize: '0.875rem', color: '#374151', lineHeight: 1.55 }}>
            This will permanently delete ALL sales records belonging to
          </p>
          <DetailRow label="Distributor Company" value={companyOf(deleteReportTarget)} />
          <DetailRow
            label="Representative"
            value={
              deleteReportTarget.distributor &&
              deleteReportTarget.distributor !== deleteReportTarget.company
                ? deleteReportTarget.distributor
                : '—'
            }
          />
          <DetailRow label="Reporting Quarter" value={reportingQuarterOf(deleteReportTarget)} />
          <p style={{ margin: '12px 0', fontSize: '0.875rem', fontWeight: 700, color: '#111827' }}>
            {deleteReportCount === null
              ? 'Calculating…'
              : `${deleteReportCount} Sales Record${deleteReportCount === 1 ? '' : 's'} will be deleted.`}
          </p>
          <p style={{ margin: '0 0 16px', fontSize: '0.8125rem', color: '#DC2626', fontWeight: 500 }}>
            This action cannot be undone.
          </p>
          {actionError && <p style={{ color: '#DC2626', fontSize: '0.8125rem' }}>{actionError}</p>}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 8 }}>
            <button
              type="button"
              disabled={actionBusy}
              onClick={() => setDeleteReportTarget(null)}
              style={modalSecondaryBtn}
            >
              Cancel
            </button>
            <button
              type="button"
              disabled={actionBusy || deleteReportCount === 0}
              onClick={confirmDeleteReport}
              style={modalReportBtn}
            >
              {actionBusy ? 'Deleting…' : 'Delete Entire Report'}
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}

function InfoCell({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div
        style={{
          fontSize: '0.625rem',
          fontWeight: 700,
          color: '#9CA3AF',
          textTransform: 'uppercase',
          letterSpacing: '0.04em',
          marginBottom: 3,
        }}
      >
        {label}
      </div>
      <div style={{ fontSize: '0.8125rem', color: '#111827', fontWeight: 500, lineHeight: 1.4 }}>{value}</div>
    </div>
  );
}

function FilterSelect({
  label,
  value,
  options,
  onChange,
  selectStyle,
  labelStyle,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (v: string) => void;
  selectStyle: React.CSSProperties;
  labelStyle: React.CSSProperties;
}) {
  return (
    <div>
      <label style={labelStyle}>{label}</label>
      <select value={value} onChange={e => onChange(e.target.value)} style={selectStyle}>
        <option value="">All</option>
        {options.map(opt => (
          <option key={opt} value={opt}>
            {opt}
          </option>
        ))}
      </select>
    </div>
  );
}

function Modal({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  return (
    <div style={overlayStyle} onClick={onClose}>
      <div
        style={{
          background: '#FFFFFF',
          borderRadius: 8,
          padding: 24,
          maxWidth: 480,
          width: '90%',
          maxHeight: '80vh',
          overflowY: 'auto',
          boxShadow: '0 8px 30px rgba(0,0,0,0.18)',
        }}
        onClick={e => e.stopPropagation()}
      >
        <h2 style={{ fontSize: '1.125rem', fontWeight: 600, color: '#1F2937', margin: '0 0 16px' }}>{title}</h2>
        {children}
      </div>
    </div>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ marginBottom: 10 }}>
      <label
        style={{
          fontSize: '0.6875rem',
          fontWeight: 600,
          color: '#6B7280',
          textTransform: 'uppercase',
          letterSpacing: '0.05em',
        }}
      >
        {label}
      </label>
      <p style={{ margin: '4px 0 0', fontSize: '0.875rem', color: '#1F2937', whiteSpace: 'pre-line' }}>{value}</p>
    </div>
  );
}

function thStyle(align: 'left' | 'right'): React.CSSProperties {
  return {
    padding: '11px 16px',
    textAlign: align,
    fontSize: '0.6875rem',
    fontWeight: 700,
    color: '#6B7280',
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
    cursor: 'pointer',
    userSelect: 'none',
    whiteSpace: 'nowrap',
  };
}

const tdMuted: React.CSSProperties = {
  padding: '12px 16px',
  fontSize: '0.8125rem',
  color: '#9CA3AF',
  fontWeight: 500,
};

const chipBlue: React.CSSProperties = {
  display: 'inline-flex',
  padding: '3px 10px',
  borderRadius: 6,
  background: 'rgba(31,95,168,0.07)',
  color: BLUE,
  fontSize: '0.8125rem',
  fontWeight: 600,
  whiteSpace: 'nowrap',
};

const actionBtn: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 4,
  height: 28,
  padding: '0 8px',
  borderRadius: 6,
  border: `1px solid ${BORDER}`,
  background: 'white',
  color: '#374151',
  fontSize: '0.6875rem',
  fontWeight: 600,
  cursor: 'pointer',
};

const actionBtnDanger: React.CSSProperties = {
  ...actionBtn,
  border: '1px solid rgba(220,38,38,0.25)',
  color: '#DC2626',
  background: 'rgba(220,38,38,0.04)',
};

const actionBtnReport: React.CSSProperties = {
  ...actionBtn,
  border: '1px solid rgba(180,83,9,0.3)',
  color: '#B45309',
  background: 'rgba(180,83,9,0.06)',
};

const overlayStyle: React.CSSProperties = {
  position: 'fixed',
  top: 0,
  left: 0,
  right: 0,
  bottom: 0,
  background: 'rgba(0, 0, 0, 0.5)',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  zIndex: 1000,
};

const iconCloseBtn: React.CSSProperties = {
  border: 'none',
  background: 'transparent',
  cursor: 'pointer',
  color: '#6B7280',
  padding: 4,
  display: 'inline-flex',
};

const modalSecondaryBtn: React.CSSProperties = {
  padding: '8px 16px',
  borderRadius: 7,
  border: `1px solid ${BORDER}`,
  background: 'white',
  fontSize: '0.8125rem',
  fontWeight: 600,
  color: '#374151',
  cursor: 'pointer',
};

const modalDangerBtn: React.CSSProperties = {
  padding: '8px 16px',
  borderRadius: 7,
  border: 'none',
  background: '#DC2626',
  fontSize: '0.8125rem',
  fontWeight: 600,
  color: 'white',
  cursor: 'pointer',
};

const modalReportBtn: React.CSSProperties = {
  padding: '8px 16px',
  borderRadius: 7,
  border: 'none',
  background: '#B45309',
  fontSize: '0.8125rem',
  fontWeight: 600,
  color: 'white',
  cursor: 'pointer',
};

function pagerBtn(disabled: boolean): React.CSSProperties {
  return {
    width: 32,
    height: 32,
    borderRadius: 7,
    border: `1px solid ${BORDER}`,
    background: 'white',
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    cursor: disabled ? 'not-allowed' : 'pointer',
    opacity: disabled ? 0.4 : 1,
    color: '#374151',
  };
}
