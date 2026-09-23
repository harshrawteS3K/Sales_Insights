import { useCallback, useEffect, useMemo, useState, Fragment, type CSSProperties } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { StatusBanner } from '../../components/common/StatusBanner';
import { EnterpriseAnalyticsFilters } from '../../components/filters/EnterpriseAnalyticsFilters';
import { ApiError } from '../../api';
import { BLUE, BORDER, TEAL } from '../../constants/theme';
import {
  DistributorService,
  type DistributorPerformancePayload,
} from '../../services/distributor.service';
import {
  defaultEnterpriseFilters,
  toAnalyticsQuery,
  validateEnterpriseFilters,
  type EnterpriseFilterOptions,
  type EnterpriseFilterState,
} from '../../utils/analyticsFilters';

const cardStyle: CSSProperties = {
  background: 'white',
  border: `1px solid ${BORDER}`,
  borderRadius: 12,
  padding: '18px 20px',
  boxShadow: '0 1px 4px rgba(0,0,0,0.04)',
};

function LeaderCard({
  title,
  name,
  sales,
  accent,
}: {
  title: string;
  name: string;
  sales: string;
  accent: string;
}) {
  return (
    <div style={cardStyle}>
      <div
        style={{
          fontSize: '0.6875rem',
          fontWeight: 700,
          color: accent,
          textTransform: 'uppercase',
          letterSpacing: '0.05em',
          marginBottom: 10,
        }}
      >
        {title}
      </div>
      <div style={{ fontSize: '1.05rem', fontWeight: 700, color: '#0F172A', marginBottom: 6 }}>
        {name}
      </div>
      <div style={{ fontSize: '1.35rem', fontWeight: 700, color: BLUE }}>{sales}</div>
    </div>
  );
}

export function DistributorPerformance() {
  const [filters, setFilters] = useState<EnterpriseFilterState>(defaultEnterpriseFilters);
  const [filterOptions, setFilterOptions] = useState<EnterpriseFilterOptions>({
    distributors: [],
    segments: [],
    locations: [],
    customers: [],
    products: [],
  });

  const [data, setData] = useState<DistributorPerformancePayload | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);

  useEffect(() => {
    DistributorService.getPerformanceFilterOptions()
      .then(opts => {
        setFilterOptions({
          distributors: opts.distributors || [],
          customers: opts.customers || [],
          products: opts.products || [],
          locations: opts.locations || [],
          segments: opts.segments || [],
          financial_years: opts.financial_years,
        });
      })
      .catch(() => undefined);
  }, []);

  const query = useMemo(() => toAnalyticsQuery(filters), [filters]);

  const runCompare = useCallback(async () => {
    const validation = validateEnterpriseFilters(filters);
    if (validation) {
      setError(validation);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const payload = await DistributorService.getPerformance(query);
      setData(payload);
      setLoaded(true);
      setExpandedId(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load distributor performance');
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [query, filters]);

  const chartData = useMemo(() => {
    return (data?.ranking || []).map(r => ({
      name: r.distributor.length > 22 ? `${r.distributor.slice(0, 20)}…` : r.distributor,
      fullName: r.distributor,
      sales: r.sales_mt,
    }));
  }, [data]);

  const chartHeight = Math.max(280, (chartData.length || 1) * 28);

  const kpis = data?.kpis;
  const ranking = data?.ranking || [];

  return (
    <div>
      {error && <StatusBanner message={error} type="error" style={{ marginBottom: 16 }} />}

      <EnterpriseAnalyticsFilters
        title="Performance Filters"
        actionLabel="Compare"
        loading={loading}
        showCountry
        value={filters}
        options={filterOptions}
        onChange={patch => setFilters(prev => ({ ...prev, ...patch }))}
        onSubmit={() => void runCompare()}
      />

      {!loaded && !loading && (
        <div
          style={{
            ...cardStyle,
            textAlign: 'center',
            color: '#64748B',
            fontSize: '0.875rem',
            padding: '48px 24px',
          }}
        >
          Set filters and click <strong>Compare</strong> to benchmark distributor performance.
        </div>
      )}

      {loaded && data && (
        <>
          {/* SECTION 2 — Leader cards */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
              gap: 14,
              marginBottom: 20,
            }}
          >
            <LeaderCard
              title="Top Performer"
              name={kpis?.top_performer.distributor || '—'}
              sales={`${kpis?.top_performer.sales_mt_display || '0'} MT`}
              accent={TEAL}
            />
            <LeaderCard
              title="Runner Up"
              name={kpis?.runner_up.distributor || '—'}
              sales={`${kpis?.runner_up.sales_mt_display || '0'} MT`}
              accent={BLUE}
            />
            <div style={cardStyle}>
              <div
                style={{
                  fontSize: '0.6875rem',
                  fontWeight: 700,
                  color: '#059669',
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                  marginBottom: 10,
                }}
              >
                Active
              </div>
              <div style={{ fontSize: '1.35rem', fontWeight: 700, color: '#0F172A' }}>
                {kpis?.active_distributors.label || '0 / 0 Distributors'}
              </div>
              <div style={{ fontSize: '0.8125rem', color: '#64748B', marginTop: 6 }}>
                Submitted sales in selected period
              </div>
            </div>
          </div>

          {/* SECTION 3 — Ranking chart */}
          <div style={{ ...cardStyle, marginBottom: 20 }}>
            <div style={{ fontSize: '0.875rem', fontWeight: 700, color: '#0F172A', marginBottom: 4 }}>
              Distributor Ranking
            </div>
            <div style={{ fontSize: '0.75rem', color: '#64748B', marginBottom: 14 }}>
              All directory distributors · sorted by sales (MT) · zeros included
            </div>
            {chartData.length === 0 ? (
              <div style={{ padding: 32, textAlign: 'center', color: '#94A3B8', fontSize: '0.8125rem' }}>
                No distributors in the Directory.
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={chartHeight}>
                <BarChart
                  layout="vertical"
                  data={chartData}
                  margin={{ top: 4, right: 24, left: 8, bottom: 4 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" horizontal={false} />
                  <XAxis
                    type="number"
                    tick={{ fontSize: 11, fill: '#6B7280' }}
                    axisLine={{ stroke: BORDER }}
                  />
                  <YAxis
                    type="category"
                    dataKey="name"
                    width={140}
                    tick={{ fontSize: 11, fill: '#374151' }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <Tooltip
                    formatter={(value: number) => [`${Number(value).toLocaleString()} MT`, 'Sales']}
                    labelFormatter={(_, payload) =>
                      (payload?.[0]?.payload?.fullName as string) || ''
                    }
                  />
                  <Bar dataKey="sales" fill={BLUE} radius={[0, 4, 4, 0]} barSize={16} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>

          {/* SECTION 4 + 5 — Table with expandable contribution */}
          <div style={{ ...cardStyle, padding: 0, overflow: 'hidden' }}>
            <div style={{ padding: '16px 20px', borderBottom: `1px solid ${BORDER}` }}>
              <div style={{ fontSize: '0.875rem', fontWeight: 700, color: '#0F172A' }}>
                Distributor Performance Table
              </div>
              <div style={{ fontSize: '0.75rem', color: '#64748B', marginTop: 2 }}>
                Click a row to expand customer contribution for the selected period
              </div>
            </div>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8125rem' }}>
                <thead>
                  <tr style={{ background: '#F9FAFB', borderBottom: `1px solid ${BORDER}` }}>
                    {['', 'Rank', 'Distributor', 'Location', 'Country', 'Customers', 'Products', 'Sales (MT)'].map(
                      h => (
                        <th
                          key={h || 'exp'}
                          style={{
                            textAlign: h === 'Sales (MT)' || h === 'Customers' || h === 'Products' || h === 'Rank' ? 'right' : 'left',
                            padding: '10px 14px',
                            fontSize: '0.6875rem',
                            fontWeight: 700,
                            color: '#6B7280',
                            textTransform: 'uppercase',
                            letterSpacing: '0.04em',
                            width: h === '' ? 36 : undefined,
                          }}
                        >
                          {h}
                        </th>
                      ),
                    )}
                  </tr>
                </thead>
                <tbody>
                  {ranking.length === 0 ? (
                    <tr>
                      <td colSpan={8} style={{ padding: 28, textAlign: 'center', color: '#94A3B8' }}>
                        No distributors to rank.
                      </td>
                    </tr>
                  ) : (
                    ranking.map(row => {
                      const open = expandedId === row.distributor_id;
                      return (
                        <Fragment key={row.distributor_id}>
                          <tr
                            onClick={() =>
                              setExpandedId(open ? null : row.distributor_id)
                            }
                            style={{
                              borderBottom: `1px solid ${BORDER}`,
                              cursor: 'pointer',
                              background: open ? 'rgba(31,95,168,0.04)' : 'white',
                            }}
                          >
                            <td style={{ padding: '10px 14px', color: '#94A3B8' }}>
                              {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                            </td>
                            <td style={{ padding: '10px 14px', textAlign: 'right', fontWeight: 700, color: BLUE }}>
                              {row.rank}
                            </td>
                            <td style={{ padding: '10px 14px', fontWeight: 600, color: '#111827' }}>
                              {row.distributor}
                            </td>
                            <td style={{ padding: '10px 14px', color: '#374151' }}>{row.location}</td>
                            <td style={{ padding: '10px 14px', color: '#374151' }}>{row.country || '—'}</td>
                            <td style={{ padding: '10px 14px', textAlign: 'right', color: '#374151' }}>
                              {row.customers}
                            </td>
                            <td style={{ padding: '10px 14px', textAlign: 'right', color: '#374151' }}>
                              {row.products}
                            </td>
                            <td
                              style={{
                                padding: '10px 14px',
                                textAlign: 'right',
                                fontWeight: 700,
                                color: row.has_sales ? '#0F172A' : '#94A3B8',
                              }}
                            >
                              {row.sales_mt_display}
                            </td>
                          </tr>
                          {open && (
                            <tr>
                              <td
                                colSpan={8}
                                style={{
                                  padding: '0 14px 16px 48px',
                                  background: '#F8FAFC',
                                  borderBottom: `1px solid ${BORDER}`,
                                }}
                              >
                                <div
                                  style={{
                                    fontSize: '0.75rem',
                                    fontWeight: 700,
                                    color: '#334155',
                                    textTransform: 'uppercase',
                                    letterSpacing: '0.04em',
                                    margin: '12px 0 8px',
                                  }}
                                >
                                  Customer Contribution
                                </div>
                                {row.customer_contribution.length === 0 ? (
                                  <div style={{ fontSize: '0.8125rem', color: '#94A3B8', fontStyle: 'italic' }}>
                                    No customers for this period (0 MT).
                                  </div>
                                ) : (
                                  <table
                                    style={{
                                      width: '100%',
                                      maxWidth: 640,
                                      borderCollapse: 'collapse',
                                      fontSize: '0.8125rem',
                                      background: 'white',
                                      border: `1px solid ${BORDER}`,
                                      borderRadius: 8,
                                      overflow: 'hidden',
                                    }}
                                  >
                                    <thead>
                                      <tr style={{ background: '#F3F4F6' }}>
                                        <th style={{ textAlign: 'left', padding: '8px 12px', fontSize: '0.6875rem', color: '#6B7280' }}>
                                          Customer Name
                                        </th>
                                        <th style={{ textAlign: 'right', padding: '8px 12px', fontSize: '0.6875rem', color: '#6B7280' }}>
                                          Product Count
                                        </th>
                                        <th style={{ textAlign: 'right', padding: '8px 12px', fontSize: '0.6875rem', color: '#6B7280' }}>
                                          Sales Quantity
                                        </th>
                                      </tr>
                                    </thead>
                                    <tbody>
                                      {row.customer_contribution.map(c => (
                                        <tr key={c.customer} style={{ borderTop: `1px solid ${BORDER}` }}>
                                          <td style={{ padding: '8px 12px', fontWeight: 600, color: '#111827' }}>
                                            {c.customer}
                                          </td>
                                          <td style={{ padding: '8px 12px', textAlign: 'right', color: '#374151' }}>
                                            {c.product_count}
                                          </td>
                                          <td style={{ padding: '8px 12px', textAlign: 'right', fontWeight: 600, color: BLUE }}>
                                            {c.sales_mt_display}
                                          </td>
                                        </tr>
                                      ))}
                                    </tbody>
                                  </table>
                                )}
                              </td>
                            </tr>
                          )}
                        </Fragment>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
