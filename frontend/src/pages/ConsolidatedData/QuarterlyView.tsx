import { useEffect, useMemo, useState, type CSSProperties } from 'react';
import { ArrowLeft, Building2, ChevronLeft, ChevronRight, Search } from 'lucide-react';
import { BLUE, BORDER } from '../../constants/theme';
import { SearchAutocomplete } from '../../components/ui/SearchAutocomplete';
import { StatusBanner } from '../../components/common/StatusBanner';
import { ConsolidatedDataService } from '../../services/consolidatedData.service';
import { ApiError } from '../../api';
import type {
  QuarterlyReportResponse,
  QuarterlySummaryResponse,
} from '../../types';

type Props = {
  quarters: string[];
  companies: string[];
};

type DetailKey = { company: string; quarter: string };

type SortKey = 'customer' | 'segment' | 'product' | 'quantity' | 'contributionPct';

const PAGE_SIZE = 10;

/**
 * Virtual Quarterly View — SQL-aggregated ACTIVE monthly data by Distributor Company.
 * Does not create or store quarterly reports.
 */
export function QuarterlyView({ quarters, companies }: Props) {
  const [quarter, setQuarter] = useState(quarters[0] || '');
  const [company, setCompany] = useState('All');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [summary, setSummary] = useState<QuarterlySummaryResponse | null>(null);
  const [detailKey, setDetailKey] = useState<DetailKey | null>(null);

  useEffect(() => {
    if (!quarter && quarters.length) setQuarter(quarters[0]);
  }, [quarters, quarter]);

  useEffect(() => {
    if (!quarter) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      setDetailKey(null);
      try {
        const data = await ConsolidatedDataService.getQuarterlySummary({
          quarter,
          company: company !== 'All' ? company : undefined,
        });
        if (!cancelled) setSummary(data);
      } catch (err) {
        if (!cancelled) {
          setSummary(null);
          setError(err instanceof ApiError ? err.message : 'Failed to load quarterly summary');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [quarter, company]);

  if (detailKey) {
    return (
      <QuarterlyReportPanel
        company={detailKey.company}
        quarter={detailKey.quarter}
        onBack={() => setDetailKey(null)}
      />
    );
  }

  return (
    <div>
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-end',
          gap: 14,
          flexWrap: 'wrap',
          marginBottom: 16,
          padding: '14px 16px',
          background: 'white',
          border: `1px solid ${BORDER}`,
          borderRadius: 10,
        }}
      >
        <div style={{ minWidth: 160 }}>
          <div style={labelStyle}>Quarter</div>
          <select
            value={quarter}
            onChange={e => setQuarter(e.target.value)}
            style={selectStyle}
          >
            {quarters.length === 0 && <option value="">No quarters available</option>}
            {quarters.map(q => (
              <option key={q} value={q}>
                {q}
              </option>
            ))}
          </select>
        </div>
        <SearchAutocomplete
          label="Distributor Company"
          options={companies}
          value={company}
          onChange={setCompany}
          placeholder="Search company…"
          allValue="All"
          width={260}
        />
        {summary && (
          <div style={{ marginLeft: 'auto', fontSize: '0.8125rem', color: '#6B7280' }}>
            {summary.totalCompanies} compan{summary.totalCompanies === 1 ? 'y' : 'ies'} ·{' '}
            {summary.grandTotalQuantity.toLocaleString()} {summary.unit}
          </div>
        )}
      </div>

      <StatusBanner loading={loading} error={error} loadingText="Loading quarterly summary…" />

      {!loading && summary && summary.data.length === 0 && (
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
          No ACTIVE monthly reports found for {quarter || 'this quarter'}.
        </div>
      )}

      {!loading && summary && summary.data.length > 0 && (
        <div
          style={{
            background: 'white',
            border: `1px solid ${BORDER}`,
            borderRadius: 12,
            overflow: 'hidden',
            boxShadow: '0 1px 4px rgba(0,0,0,0.04)',
          }}
        >
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 900 }}>
              <thead>
                <tr style={{ background: '#F3F4F6', borderBottom: `1px solid ${BORDER}` }}>
                  {[
                    'Distributor Company',
                    'Quarter',
                    'Total Quantity (MT)',
                    'Products Sold',
                    'Reports Included',
                    'Months Submitted',
                  ].map(h => (
                    <th
                      key={h}
                      style={{
                        padding: '10px 14px',
                        textAlign: 'left',
                        fontSize: '0.6875rem',
                        fontWeight: 700,
                        color: '#6B7280',
                        textTransform: 'uppercase',
                        letterSpacing: '0.03em',
                      }}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {summary.data.map(row => (
                  <tr
                    key={row.company}
                    onClick={() =>
                      setDetailKey({ company: row.company, quarter: row.quarter })
                    }
                    style={{
                      borderBottom: `1px solid ${BORDER}`,
                      cursor: 'pointer',
                    }}
                    onMouseEnter={e => {
                      e.currentTarget.style.background = '#F8FAFC';
                    }}
                    onMouseLeave={e => {
                      e.currentTarget.style.background = 'white';
                    }}
                  >
                    <td style={tdStyle}>
                      <div
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: 8,
                          fontWeight: 600,
                        }}
                      >
                        <Building2 size={14} color={BLUE} />
                        {row.company}
                      </div>
                      {row.isPartial && (
                        <div style={{ fontSize: '0.6875rem', color: '#B45309', marginTop: 2 }}>
                          Partial quarter ({row.monthsSubmitted.length}/
                          {row.monthsExpected.length} months)
                        </div>
                      )}
                    </td>
                    <td style={tdStyle}>{row.quarter}</td>
                    <td style={tdStyle}>{row.totalQuantityDisplay}</td>
                    <td style={tdStyle}>{row.productsSold}</td>
                    <td style={tdStyle}>{row.reportsIncluded}</td>
                    <td style={tdStyle}>{row.monthsSubmitted.join(', ') || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

function QuarterlyReportPanel({
  company,
  quarter,
  onBack,
}: {
  company: string;
  quarter: string;
  onBack: () => void;
}) {
  const [report, setReport] = useState<QuarterlyReportResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [searchInput, setSearchInput] = useState('');
  const [search, setSearch] = useState('');
  const [sortBy, setSortBy] = useState<SortKey>('quantity');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');

  useEffect(() => {
    const t = window.setTimeout(() => {
      const next = searchInput.trim();
      setSearch(prev => {
        if (prev !== next) {
          setPage(1);
        }
        return next;
      });
    }, 300);
    return () => window.clearTimeout(t);
  }, [searchInput]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await ConsolidatedDataService.getQuarterlyReport({
          company,
          quarter,
          page,
          page_size: PAGE_SIZE,
          search: search || undefined,
          sort_by: sortBy,
          sort_order: sortOrder,
        });
        if (!cancelled) setReport(data);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : 'Failed to load quarterly report');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [company, quarter, page, search, sortBy, sortOrder]);

  const pageButtons = useMemo(() => {
    const total = report?.totalPages ?? 0;
    if (total <= 0) return [];
    const cur = report?.currentPage ?? page;
    const pages: (number | '…')[] = [];
    const push = (n: number | '…') => {
      if (pages[pages.length - 1] !== n) pages.push(n);
    };
    push(1);
    for (let i = Math.max(2, cur - 1); i <= Math.min(total - 1, cur + 1); i++) {
      if (i > 2 && pages[pages.length - 1] !== '…' && i > (pages[pages.length - 1] as number) + 1) {
        push('…');
      }
      push(i);
    }
    if (total > 1) {
      if (total > 2 && (pages[pages.length - 1] as number) < total - 1) push('…');
      push(total);
    }
    return pages;
  }, [report, page]);

  const toggleSort = (key: SortKey) => {
    if (sortBy === key) {
      setSortOrder(o => (o === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortBy(key);
      setSortOrder(key === 'quantity' || key === 'contributionPct' ? 'desc' : 'asc');
    }
    setPage(1);
  };

  const sortMark = (key: SortKey) => {
    if (sortBy !== key) return '';
    return sortOrder === 'asc' ? ' ↑' : ' ↓';
  };

  return (
    <div>
      <button type="button" onClick={onBack} style={backBtn}>
        <ArrowLeft size={14} />
        Back to quarterly summary
      </button>

      {report && (
        <div
          style={{
            background: 'white',
            border: `1px solid ${BORDER}`,
            borderRadius: 12,
            padding: '18px 20px',
            marginBottom: 16,
            boxShadow: '0 1px 4px rgba(0,0,0,0.04)',
          }}
        >
          <div style={{ fontSize: '1.0625rem', fontWeight: 700, color: '#111827' }}>
            {report.company}
            <span style={{ color: '#9CA3AF', fontWeight: 500 }}> · </span>
            <span style={{ color: '#374151' }}>{report.period.label}</span>
          </div>
          <div style={{ marginTop: 6, fontSize: '0.8125rem', color: '#6B7280' }}>
            Virtual quarterly report · ACTIVE monthly data only · Not stored
          </div>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
              gap: 10,
              marginTop: 14,
            }}
          >
            <Stat label="Total Quantity (MT)" value={report.totalQuantityDisplay} />
            <Stat label="Products Sold" value={String(report.productsSold)} />
            <Stat label="Customers" value={String(report.customerCount)} />
            <Stat label="Reports Included" value={String(report.reportsIncluded)} />
            <Stat
              label="Months Submitted"
              value={report.monthsSubmitted.join(', ') || '—'}
            />
          </div>
          {report.isPartial && (
            <div
              style={{
                marginTop: 12,
                padding: '8px 10px',
                background: 'rgba(180,83,9,0.08)',
                border: '1px solid rgba(180,83,9,0.25)',
                borderRadius: 6,
                color: '#92400E',
                fontSize: '0.75rem',
              }}
            >
              Partial quarter — expected {report.monthsExpected.join(', ')}.
            </div>
          )}
        </div>
      )}

      <StatusBanner loading={loading && !report} error={error} loadingText="Loading…" />

      <div
        style={{
          background: 'white',
          border: `1px solid ${BORDER}`,
          borderRadius: 12,
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            padding: '12px 16px',
            borderBottom: `1px solid ${BORDER}`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 12,
            flexWrap: 'wrap',
          }}
        >
          <div style={{ fontSize: '0.8125rem', fontWeight: 600, color: '#111827' }}>
            Quarterly Detail
            <span style={{ color: '#9CA3AF', fontWeight: 500 }}>
              {' '}
              · Customer → Segment → Product
            </span>
          </div>
          <div style={{ position: 'relative', minWidth: 240, flex: '1 1 240px', maxWidth: 360 }}>
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
              type="search"
              value={searchInput}
              onChange={e => setSearchInput(e.target.value)}
              placeholder="Search customer, segment, product…"
              style={{
                width: '100%',
                height: 34,
                padding: '0 12px 0 32px',
                border: `1px solid ${BORDER}`,
                borderRadius: 6,
                fontSize: '0.8125rem',
                color: '#374151',
                fontFamily: 'inherit',
              }}
            />
          </div>
        </div>

        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 720 }}>
            <thead>
              <tr style={{ background: '#F3F4F6', borderBottom: `1px solid ${BORDER}` }}>
                <th style={thStyle}>Sr. No</th>
                <th style={{ ...thStyle, cursor: 'pointer' }} onClick={() => toggleSort('customer')}>
                  Customer{sortMark('customer')}
                </th>
                <th style={{ ...thStyle, cursor: 'pointer' }} onClick={() => toggleSort('segment')}>
                  Segment{sortMark('segment')}
                </th>
                <th style={{ ...thStyle, cursor: 'pointer' }} onClick={() => toggleSort('product')}>
                  Product{sortMark('product')}
                </th>
                <th style={{ ...thStyle, cursor: 'pointer' }} onClick={() => toggleSort('quantity')}>
                  Quantity (MT){sortMark('quantity')}
                </th>
                <th
                  style={{ ...thStyle, cursor: 'pointer' }}
                  onClick={() => toggleSort('contributionPct')}
                >
                  Contribution %{sortMark('contributionPct')}
                </th>
              </tr>
            </thead>
            <tbody>
              {(report?.items ?? []).map(row => (
                <tr
                  key={`${row.srNo}-${row.customer}-${row.segment}-${row.product}`}
                  style={{ borderBottom: `1px solid ${BORDER}` }}
                >
                  <td style={tdStyle}>{row.srNo}</td>
                  <td style={tdStyle}>{row.customer}</td>
                  <td style={tdStyle}>{row.segment}</td>
                  <td style={tdStyle}>{row.product}</td>
                  <td style={tdStyle}>{row.quantityDisplay}</td>
                  <td style={tdStyle}>{row.contributionPct}%</td>
                </tr>
              ))}
              {!loading && (report?.items.length ?? 0) === 0 && (
                <tr>
                  <td colSpan={6} style={{ ...tdStyle, textAlign: 'center', color: '#9CA3AF' }}>
                    No matching rows for this quarter
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {report && report.totalRecords > 0 && (
          <div
            style={{
              padding: '10px 16px',
              borderTop: `1px solid ${BORDER}`,
              background: '#F9FAFB',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 12,
              flexWrap: 'wrap',
              fontSize: '0.8125rem',
              color: '#6B7280',
            }}
          >
            <span>
              Showing{' '}
              {(report.currentPage - 1) * report.pageSize + 1}–
              {Math.min(report.currentPage * report.pageSize, report.totalRecords)} of{' '}
              {report.totalRecords}
            </span>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <button
                type="button"
                disabled={report.currentPage <= 1 || loading}
                onClick={() => setPage(p => Math.max(1, p - 1))}
                style={pagerBtn(report.currentPage <= 1 || loading)}
              >
                <ChevronLeft size={14} />
                Previous
              </button>
              {pageButtons.map((p, i) =>
                p === '…' ? (
                  <span key={`e-${i}`} style={{ padding: '0 4px', color: '#9CA3AF' }}>
                    …
                  </span>
                ) : (
                  <button
                    key={p}
                    type="button"
                    disabled={loading}
                    onClick={() => setPage(p)}
                    style={{
                      ...pagerBtn(false),
                      minWidth: 32,
                      background: p === report.currentPage ? BLUE : 'white',
                      color: p === report.currentPage ? 'white' : '#374151',
                      borderColor: p === report.currentPage ? BLUE : BORDER,
                      fontWeight: p === report.currentPage ? 700 : 500,
                    }}
                  >
                    {p}
                  </button>
                )
              )}
              <button
                type="button"
                disabled={report.currentPage >= report.totalPages || loading}
                onClick={() => setPage(p => p + 1)}
                style={pagerBtn(report.currentPage >= report.totalPages || loading)}
              >
                Next
                <ChevronRight size={14} />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div
      style={{
        background: '#F8FAFC',
        borderRadius: 8,
        padding: '8px 10px',
        border: `1px solid ${BORDER}`,
      }}
    >
      <div
        style={{
          fontSize: '0.625rem',
          color: '#6B7280',
          fontWeight: 700,
          textTransform: 'uppercase',
        }}
      >
        {label}
      </div>
      <div style={{ fontSize: '0.875rem', fontWeight: 700, color: '#111827', marginTop: 2 }}>
        {value}
      </div>
    </div>
  );
}

const labelStyle: CSSProperties = {
  fontSize: '0.65rem',
  color: '#6B7280',
  fontWeight: 600,
  marginBottom: 3,
};

const selectStyle: CSSProperties = {
  height: 32,
  width: '100%',
  padding: '0 10px',
  border: `1px solid ${BORDER}`,
  borderRadius: 6,
  fontSize: '0.8125rem',
  color: '#374151',
  background: 'white',
};

const tdStyle: CSSProperties = {
  padding: '12px 14px',
  fontSize: '0.8125rem',
  color: '#374151',
  verticalAlign: 'top',
};

const thStyle: CSSProperties = {
  padding: '10px 14px',
  textAlign: 'left',
  fontSize: '0.6875rem',
  fontWeight: 700,
  color: '#6B7280',
  textTransform: 'uppercase',
  whiteSpace: 'nowrap',
  userSelect: 'none',
};

const backBtn: CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 6,
  marginBottom: 14,
  border: 'none',
  background: 'transparent',
  color: BLUE,
  fontSize: '0.8125rem',
  fontWeight: 600,
  cursor: 'pointer',
  fontFamily: 'inherit',
  padding: 0,
};

function pagerBtn(disabled: boolean): CSSProperties {
  return {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 4,
    height: 32,
    padding: '0 10px',
    border: `1px solid ${BORDER}`,
    borderRadius: 6,
    background: 'white',
    color: disabled ? '#9CA3AF' : '#374151',
    fontSize: '0.75rem',
    fontWeight: 600,
    cursor: disabled ? 'not-allowed' : 'pointer',
    fontFamily: 'inherit',
    opacity: disabled ? 0.7 : 1,
  };
}
