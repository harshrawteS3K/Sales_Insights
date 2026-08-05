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
} from 'lucide-react';
import { BLUE, BORDER } from '../../constants/theme';
import type {
  ReportSalesGroup,
  SalesLineItem,
  SortKey,
  ConsolidatedFilterOptions,
  ConsolidatedRecordQuery,
} from '../../types';
import { ConsolidatedDataService } from '../../services/consolidatedData.service';
import { AuditTrailService } from '../../services/auditTrail.service';
import { ApiError, getSession } from '../../api';
import { isAdminRole } from '../../utils/rbac';
import { StatusBanner } from '../../components/common/StatusBanner';
import { DataQualityWarning } from '../../components/ui/DataQualityWarning';
import { SearchAutocomplete } from '../../components/ui/SearchAutocomplete';
import { QuarterlyView } from './QuarterlyView';

type FilterState = {
  distributor: string;
  customer: string;
  segment: string;
  product: string;
  company: string;
  reportingMonth: string;
  quarter: string;
  quantityMin: string;
  quantityMax: string;
  importedFrom: string;
  importedTo: string;
};

const EMPTY_FILTERS: FilterState = {
  distributor: '',
  customer: '',
  segment: '',
  product: '',
  company: '',
  reportingMonth: '',
  quarter: '',
  quantityMin: '',
  quantityMax: '',
  importedFrom: '',
  importedTo: '',
};

const PAGE_SIZE = 50;
const EXPAND_ALL_THRESHOLD = 3;

type ViewTarget = { report: ReportSalesGroup; line: SalesLineItem };
type DeleteRecordTarget = { report: ReportSalesGroup; line: SalesLineItem };

function reportingMonthOf(report: ReportSalesGroup): string {
  return report.reportingMonth?.trim() || '—';
}

/** Primary business entity label for reporting. */
function companyOf(report: ReportSalesGroup): string {
  return (report.company || report.distributor || '').trim() || '—';
}

function formatPhone(phone?: string | null): string {
  if (!phone) return '';
  return phone.startsWith('Ph') ? phone : `Ph. ${phone}`;
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
  const [filterOptions, setFilterOptions] = useState<ConsolidatedFilterOptions>({
    distributors: [],
    customers: [],
    segments: [],
    products: [],
    companies: [],
    reportingMonths: [],
    periods: [],
    quarters: [],
  });

  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set());
  const [viewTarget, setViewTarget] = useState<ViewTarget | null>(null);
  const [deleteRecordTarget, setDeleteRecordTarget] = useState<DeleteRecordTarget | null>(null);
  const [deleteReportTarget, setDeleteReportTarget] = useState<ReportSalesGroup | null>(null);
  const [deleteReportCount, setDeleteReportCount] = useState<number | null>(null);
  const [actionBusy, setActionBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<'monthly' | 'quarterly'>('monthly');

  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pendingAudit = useRef(false);

  const reportingMonthOptions = useMemo(
    () => filterOptions.reportingMonths?.length
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
      const month = f.reportingMonth || undefined;
      return {
        skip: opts?.skip ?? page * PAGE_SIZE,
        limit: opts?.limit ?? PAGE_SIZE,
        search: search || undefined,
        distributor: f.distributor || undefined,
        customer: f.customer || undefined,
        segment: f.segment || undefined,
        product: f.product || undefined,
        company: f.company || undefined,
        reportingMonth: month,
        period: month,
        quarter: f.quarter || undefined,
        quantity_min: f.quantityMin || undefined,
        quantity_max: f.quantityMax || undefined,
        imported_from: f.importedFrom || undefined,
        imported_to: f.importedTo || undefined,
        sort_by: sortKey,
        sort_dir: sortDir,
        audit: opts?.audit,
      };
    },
    [appliedFilters, page, search, sortKey, sortDir]
  );

  const syncExpanded = useCallback((groups: ReportSalesGroup[]) => {
    if (groups.length === 0) {
      setExpandedIds(new Set());
      return;
    }
    if (groups.length <= EXPAND_ALL_THRESHOLD) {
      setExpandedIds(new Set(groups.map(g => g.reportId)));
      return;
    }
    setExpandedIds(new Set([groups[0].reportId]));
  }, []);

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

  const exportExcel = async () => {
    try {
      const all = await ConsolidatedDataService.getSalesRecords({
        ...buildQuery({ skip: 0, limit: Math.min(Math.max(total, 1), 5000) }),
      });
      const csvRows: string[] = [];
      let exportedLines = 0;

      all.data.forEach(report => {
        const month = reportingMonthOf(report);
        const detailLines = [
          report.distributor,
          report.company || '',
          report.address || '',
          formatPhone(report.phone),
          `Reporting Month: ${month}`,
        ].filter(Boolean);

        csvRows.push(csvEscape(detailLines.join('\n')));
        csvRows.push(
          ['Sr No', 'Customer', 'Segment', 'Product', 'Quantity (MT)', 'Opening Stock', 'Closing Stock']
            .map(csvEscape)
            .join(',')
        );

        report.sales.forEach(line => {
          exportedLines += 1;
          csvRows.push(
            [
              line.srNo,
              line.customerName,
              line.segment,
              line.product,
              line.quantity,
              line.openingStock ?? '',
              line.closingStock ?? '',
            ]
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
        `consolidated_sales_data_${new Date().toISOString().split('T')[0]}.csv`
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
    const month = report.reportingMonth?.trim();
    if (!month) {
      setActionError('Reporting month is missing for this report.');
      setDeleteReportCount(0);
      return;
    }
    try {
      const preview = await ConsolidatedDataService.previewDeleteReport(
        report.company || report.distributor,
        month
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
    const month = deleteReportTarget.reportingMonth?.trim();
    if (!month) {
      setActionError('Reporting month is missing for this report.');
      return;
    }
    setActionBusy(true);
    setActionError(null);
    try {
      await ConsolidatedDataService.deleteReport(
        deleteReportTarget.company || deleteReportTarget.distributor,
        month
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

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
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
          Master repository of distributor company sales — ACTIVE monthly reports (quantity in MT)
        </p>
      </div>

      {/* View mode toggle */}
      <div
        style={{
          display: 'flex',
          gap: 4,
          marginBottom: 16,
          background: '#F3F4F6',
          padding: 4,
          borderRadius: 10,
          width: 'fit-content',
        }}
      >
        {(
          [
            { key: 'monthly' as const, label: 'Monthly' },
            { key: 'quarterly' as const, label: 'Quarterly' },
          ] as const
        ).map(({ key, label }) => (
          <button
            key={key}
            type="button"
            onClick={() => {
              setViewMode(key);
              void AuditTrailService.recordEvent({
                action: key === 'quarterly' ? 'Quarterly View Opened' : 'Monthly View Opened',
                module: 'Consolidated Data',
                description: `Switched Consolidated Data to ${label} view`,
                status: 'Info',
                entity_type: 'consolidated_data',
              });
            }}
            style={{
              padding: '8px 18px',
              borderRadius: 7,
              border: 'none',
              background: viewMode === key ? 'white' : 'transparent',
              color: viewMode === key ? BLUE : '#6B7280',
              fontWeight: viewMode === key ? 700 : 500,
              fontSize: '0.875rem',
              cursor: 'pointer',
              boxShadow: viewMode === key ? '0 1px 4px rgba(0,0,0,0.08)' : 'none',
              fontFamily: 'inherit',
            }}
          >
            {label}
          </button>
        ))}
      </div>

      {viewMode === 'quarterly' ? (
        <QuarterlyView
          quarters={filterOptions.quarters || []}
          companies={filterOptions.companies?.length ? filterOptions.companies : filterOptions.distributors || []}
        />
      ) : (
        <>
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
                placeholder="Search distributor, company, customer, product, segment, reporting month…"
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
              No reports match your search or filters.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {reportGroups.map(report => {
                const expanded = expandedIds.has(report.reportId);
                const month = reportingMonthOf(report);
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
                          }}
                        >
                          {companyOf(report)}
                          <span style={{ color: '#9CA3AF', fontWeight: 500 }}> · </span>
                          <span style={{ color: '#374151', fontWeight: 600 }}>{month}</span>
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
                          <span>{report.recordCount} sales line{report.recordCount === 1 ? '' : 's'}</span>
                          {report.senderName && <span>Sender: {report.senderName}</span>}
                          {report.importedAt && <span>Imported: {report.importedAt}</span>}
                        </div>
                      </div>
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
                            <InfoCell label="Address" value={report.address || '—'} />
                            <InfoCell label="Phone" value={formatPhone(report.phone) || '—'} />
                            <InfoCell label="Reporting Month" value={month} />
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
                                <th onClick={() => handleSort('segment')} style={thStyle('left')}>
                                  <div style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                                    Segment <SortIcon col="segment" />
                                  </div>
                                </th>
                                <th onClick={() => handleSort('product')} style={thStyle('left')}>
                                  <div style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                                    Product <SortIcon col="product" />
                                  </div>
                                </th>
                                <th onClick={() => handleSort('quantity')} style={thStyle('right')}>
                                  <div style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                                    Quantity (MT) <SortIcon col="quantity" />
                                  </div>
                                </th>
                                <th onClick={() => handleSort('openingStock')} style={thStyle('right')}>
                                  <div style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                                    Opening Stock <SortIcon col="openingStock" />
                                  </div>
                                </th>
                                <th onClick={() => handleSort('closingStock')} style={thStyle('right')}>
                                  <div style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                                    Closing Stock <SortIcon col="closingStock" />
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
                                  <td style={{ padding: '12px 16px', fontSize: '0.875rem', color: '#374151' }}>
                                    {line.segment}
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
                                  <td
                                    style={{
                                      padding: '12px 16px',
                                      fontSize: '0.875rem',
                                      color: '#374151',
                                      textAlign: 'right',
                                      whiteSpace: 'nowrap',
                                    }}
                                  >
                                    {line.openingStock ?? '—'}
                                  </td>
                                  <td
                                    style={{
                                      padding: '12px 16px',
                                      fontSize: '0.875rem',
                                      color: '#374151',
                                      textAlign: 'right',
                                      whiteSpace: 'nowrap',
                                    }}
                                  >
                                    {line.closingStock ?? '—'}
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
                                    colSpan={8}
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
              Showing {pageSalesCount === 0 ? 0 : page * PAGE_SIZE + 1}–
              {page * PAGE_SIZE + pageSalesCount} of {total} sales rows
              {totalReports > 0 && (
                <span style={{ color: '#9CA3AF' }}>
                  {' '}
                  · {reportGroups.length} report{reportGroups.length === 1 ? '' : 's'} on this page
                </span>
              )}
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
      {viewMode === 'monthly' && showFilters && (
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
              <FilterSelect
                label="Segment"
                value={filters.segment}
                options={filterOptions.segments}
                onChange={v => setFilters(f => ({ ...f, segment: v }))}
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
                label="Reporting Month"
                value={filters.reportingMonth}
                options={reportingMonthOptions}
                onChange={v => setFilters(f => ({ ...f, reportingMonth: v }))}
                selectStyle={selectStyle}
                labelStyle={labelStyle}
              />
              <FilterSelect
                label="Quarter"
                value={filters.quarter}
                options={filterOptions.quarters}
                onChange={v => setFilters(f => ({ ...f, quarter: v }))}
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
            <DetailRow label="Reporting Month" value={reportingMonthOf(viewTarget.report)} />
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
          <DetailRow label="Segment" value={viewTarget.line.segment} />
          <DetailRow label="Product" value={viewTarget.line.product} />
          <DetailRow label="Quantity (MT)" value={viewTarget.line.quantity} />
          <DetailRow label="Opening Stock" value={viewTarget.line.openingStock ?? '—'} />
          <DetailRow label="Closing Stock" value={viewTarget.line.closingStock ?? '—'} />
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
            {reportingMonthOf(deleteRecordTarget.report)}
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
          <DetailRow label="Reporting Month" value={reportingMonthOf(deleteReportTarget)} />
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
        </>
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
