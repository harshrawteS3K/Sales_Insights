import { useEffect, useState, type CSSProperties } from 'react';
import { ArrowLeft, Building2 } from 'lucide-react';
import { BLUE, BORDER } from '../../constants/theme';
import { SearchAutocomplete } from '../../components/ui/SearchAutocomplete';
import { StatusBanner } from '../../components/common/StatusBanner';
import { ConsolidatedDataService } from '../../services/consolidatedData.service';
import { ApiError } from '../../api';
import type {
  QuarterlyReportResponse,
  QuarterlySummaryRow,
  QuarterlySummaryResponse,
} from '../../types';

type Props = {
  quarters: string[];
  companies: string[];
};

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
  const [detail, setDetail] = useState<QuarterlyReportResponse | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  useEffect(() => {
    if (!quarter && quarters.length) setQuarter(quarters[0]);
  }, [quarters, quarter]);

  useEffect(() => {
    if (!quarter) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      setDetail(null);
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

  const openDetail = async (row: QuarterlySummaryRow) => {
    setDetailLoading(true);
    setError(null);
    try {
      const report = await ConsolidatedDataService.getQuarterlyReport({
        quarter: row.quarter,
        company: row.company,
      });
      setDetail(report);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load quarterly report');
    } finally {
      setDetailLoading(false);
    }
  };

  if (detail) {
    return (
      <QuarterlyReportPanel
        report={detail}
        loading={detailLoading}
        onBack={() => setDetail(null)}
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
                    onClick={() => openDetail(row)}
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
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600 }}>
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
  report,
  loading,
  onBack,
}: {
  report: QuarterlyReportResponse;
  loading: boolean;
  onBack: () => void;
}) {
  return (
    <div>
      <button
        type="button"
        onClick={onBack}
        style={{
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
        }}
      >
        <ArrowLeft size={14} />
        Back to quarterly summary
      </button>

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

      <StatusBanner loading={loading} error={null} loadingText="Loading…" />

      <div
        style={{
          background: 'white',
          border: `1px solid ${BORDER}`,
          borderRadius: 12,
          overflow: 'hidden',
        }}
      >
        <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 640 }}>
          <thead>
            <tr style={{ background: '#F3F4F6', borderBottom: `1px solid ${BORDER}` }}>
              {['Product', 'Quantity (MT)', 'Contribution %', 'Customer Count'].map(
                h => (
                  <th
                    key={h}
                    style={{
                      padding: '10px 14px',
                      textAlign: 'left',
                      fontSize: '0.6875rem',
                      fontWeight: 700,
                      color: '#6B7280',
                      textTransform: 'uppercase',
                    }}
                  >
                    {h}
                  </th>
                )
              )}
            </tr>
          </thead>
          <tbody>
            {report.products.map(p => (
              <tr key={p.product} style={{ borderBottom: `1px solid ${BORDER}` }}>
                <td style={tdStyle}>{p.product}</td>
                <td style={tdStyle}>{p.quantityDisplay}</td>
                <td style={tdStyle}>{p.contributionPct}%</td>
                <td style={tdStyle}>{p.customerCount}</td>
              </tr>
            ))}
            {report.products.length === 0 && (
              <tr>
                <td colSpan={4} style={{ ...tdStyle, textAlign: 'center', color: '#9CA3AF' }}>
                  No product data for this quarter
                </td>
              </tr>
            )}
          </tbody>
        </table>
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
      <div style={{ fontSize: '0.625rem', color: '#6B7280', fontWeight: 700, textTransform: 'uppercase' }}>
        {label}
      </div>
      <div style={{ fontSize: '0.875rem', fontWeight: 700, color: '#111827', marginTop: 2 }}>{value}</div>
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
