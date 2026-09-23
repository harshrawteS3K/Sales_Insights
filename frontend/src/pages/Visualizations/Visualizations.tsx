import { useCallback, useEffect, useMemo, useState, type CSSProperties } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { Download, Search } from 'lucide-react';
import { BLUE, BORDER, PRODUCT_COLORS, TEAL } from '../../constants/theme';
import { KpiCard } from '../../components/ui/KpiCard';
import { ChartCard } from '../../components/ui/ChartCard';
import { EnterpriseAnalyticsFilters } from '../../components/filters/EnterpriseAnalyticsFilters';
import { StatusBanner } from '../../components/common/StatusBanner';
import { ApiError } from '../../api';
import {
  VisualizationsService,
  type SalesInsightsPayload,
} from '../../services/visualizations.service';
import {
  defaultEnterpriseFilters,
  toAnalyticsQuery,
  validateEnterpriseFilters,
  type EnterpriseFilterOptions,
  type EnterpriseFilterState,
} from '../../utils/analyticsFilters';
import { formatPeriodDisplay } from '../../utils/quarter';

const btnPrimary: CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 6,
  height: 32,
  padding: '0 14px',
  borderRadius: 6,
  border: 'none',
  background: BLUE,
  color: 'white',
  fontSize: '0.8125rem',
  fontWeight: 600,
  cursor: 'pointer',
};

const btnSecondary: React.CSSProperties = {
  ...btnPrimary,
  background: 'white',
  color: '#374151',
  border: `1px solid ${BORDER}`,
};

export function Visualizations() {
  const [filters, setFilters] = useState<EnterpriseFilterState>(defaultEnterpriseFilters);
  const [filterOptions, setFilterOptions] = useState<EnterpriseFilterOptions>({
    distributors: [],
    segments: [],
    locations: [],
    customers: [],
    products: [],
  });

  const [data, setData] = useState<SalesInsightsPayload | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tableSearch, setTableSearch] = useState('');
  const [page, setPage] = useState(1);
  const [exporting, setExporting] = useState(false);

  const pageSize = 25;

  useEffect(() => {
    VisualizationsService.getFilterOptions()
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

  const queryBase = useMemo(() => toAnalyticsQuery(filters), [filters]);

  const runView = useCallback(
    async (nextPage = 1, searchOverride?: string) => {
      const validation = validateEnterpriseFilters(filters);
      if (validation) {
        setError(validation);
        return;
      }
      setLoading(true);
      setError(null);
      try {
        const payload = await VisualizationsService.getSalesInsights({
          ...queryBase,
          search: searchOverride !== undefined ? searchOverride : tableSearch || null,
          page: nextPage,
          page_size: pageSize,
        });
        setData(payload);
        setPage(nextPage);
        setLoaded(true);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : 'Failed to load sales insights');
      } finally {
        setLoading(false);
      }
    },
    [queryBase, filters, tableSearch],
  );

  const onExport = async () => {
    setExporting(true);
    setError(null);
    try {
      await VisualizationsService.exportExcel({
        ...queryBase,
        search: tableSearch || null,
      });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Export failed');
    } finally {
      setExporting(false);
    }
  };

  const kpis = data?.kpis;
  const totalPages = Math.max(1, Math.ceil((data?.table.total || 0) / pageSize));

  const topCustomerChart = (data?.top_customers || []).map(r => ({
    name: r.customer.length > 28 ? `${r.customer.slice(0, 26)}...` : r.customer,
    fullName: r.customer,
    qty: r.qty,
  }));

  return (
    <div style={{ padding: '24px 28px', maxWidth: 1280 }}>
      <div style={{ marginBottom: 20 }}>
        <h1 style={{ margin: 0, fontSize: '1.35rem', fontWeight: 700, color: '#0F172A' }}>
          Visualizations & Analytics
        </h1>
        <p style={{ margin: '6px 0 0', fontSize: '0.875rem', color: '#64748B' }}>
          Interactive sales analytics powered by structured distributor secondary sales data.
        </p>
      </div>

      {error && <StatusBanner message={error} type="error" style={{ marginBottom: 16 }} />}

      <EnterpriseAnalyticsFilters
        title="Sales Insight Filters"
        actionLabel="View"
        loading={loading}
        value={filters}
        options={filterOptions}
        onChange={patch => setFilters(prev => ({ ...prev, ...patch }))}
        onSubmit={() => void runView(1)}
      />

      {!loaded && !loading && (
        <div
          style={{
            padding: '48px 24px',
            textAlign: 'center',
            color: '#94A3B8',
            background: 'white',
            border: `1px dashed ${BORDER}`,
            borderRadius: 12,
          }}
        >
          Set filters and click <strong>View</strong> to load sales insights.
        </div>
      )}

      {loaded && data && (
        <>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(4, minmax(0, 1fr))',
              gap: 14,
              marginBottom: 20,
            }}
          >
            <KpiCard label="Total Sales (MT)" value={kpis?.total_sales_mt_display || '0'} valueColor={BLUE} />
            <KpiCard label="Total Customers" value={String(kpis?.total_customers ?? 0)} />
            <KpiCard label="Total Products" value={String(kpis?.total_products ?? 0)} />
            <KpiCard
              label="Average Quarterly Sales (MT)"
              value={kpis?.avg_monthly_sales_mt_display || '0'}
              valueColor={TEAL}
            />
          </div>

          <ChartCard
            title="Sales Trend"
            subtitle="Sales Quantity (MT) by month for the selected period"
            style={{ marginBottom: 20 }}
          >
            <div style={{ width: '100%', height: 300 }}>
              <ResponsiveContainer>
                <LineChart data={data.monthly_trend} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
                  <XAxis dataKey="month" tick={{ fontSize: 11, fill: '#6B7280' }} />
                  <YAxis tick={{ fontSize: 11, fill: '#6B7280' }} />
                  <Tooltip
                    formatter={(value: number) => [`${value} MT`, 'Sales']}
                    labelFormatter={(_label, payload) =>
                      String(payload?.[0]?.payload?.tooltip || _label || '')
                    }
                  />
                  <Legend />
                  <Line
                    type="monotone"
                    dataKey="qty"
                    name="Sales (MT)"
                    stroke={BLUE}
                    strokeWidth={2.5}
                    dot={{ r: 3 }}
                    activeDot={{ r: 5 }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </ChartCard>

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'minmax(0, 1.2fr) minmax(0, 1fr)',
              gap: 16,
              marginBottom: 20,
            }}
          >
            <ChartCard title="Top Customers" subtitle="Top 10 by Sales Quantity (MT)">
              <div style={{ width: '100%', height: 340 }}>
                <ResponsiveContainer>
                  <BarChart
                    data={topCustomerChart}
                    layout="vertical"
                    margin={{ top: 8, right: 16, left: 8, bottom: 0 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
                    <XAxis type="number" tick={{ fontSize: 11, fill: '#6B7280' }} />
                    <YAxis
                      type="category"
                      dataKey="name"
                      width={120}
                      tick={{ fontSize: 11, fill: '#6B7280' }}
                    />
                    <Tooltip
                      formatter={(value: number) => [`${value} MT`, 'Sales']}
                      labelFormatter={(_, payload) =>
                        (payload?.[0]?.payload?.fullName as string) || ''
                      }
                    />
                    <Bar dataKey="qty" name="Sales MT" fill={TEAL} radius={[0, 4, 4, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </ChartCard>

            <ChartCard title="Product Contribution" subtitle="Share of Sales Quantity (MT)">
              <div style={{ width: '100%', height: 340 }}>
                <ResponsiveContainer>
                  <PieChart>
                    <Pie
                      data={data.product_contribution}
                      dataKey="qty"
                      nameKey="product"
                      cx="50%"
                      cy="50%"
                      innerRadius={58}
                      outerRadius={100}
                      paddingAngle={2}
                    >
                      {data.product_contribution.map((_, idx) => (
                        <Cell key={idx} fill={PRODUCT_COLORS[idx % PRODUCT_COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip formatter={(value: number) => [`${value} MT`, 'Sales']} />
                    <Legend />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            </ChartCard>
          </div>

          <div
            style={{
              background: 'white',
              border: `1px solid ${BORDER}`,
              borderRadius: 12,
              padding: '18px 20px',
              boxShadow: '0 1px 4px rgba(0,0,0,0.04)',
            }}
          >
            <div
              style={{
                display: 'flex',
                flexWrap: 'wrap',
                gap: 12,
                alignItems: 'center',
                justifyContent: 'space-between',
                marginBottom: 14,
              }}
            >
              <div>
                <div style={{ fontSize: '0.9375rem', fontWeight: 700, color: '#111827' }}>
                  Detailed Sales Table
                </div>
                <div style={{ fontSize: '0.75rem', color: '#9CA3AF' }}>
                  {data.table.total.toLocaleString()} filtered record(s)
                </div>
              </div>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 6,
                    height: 32,
                    padding: '0 10px',
                    border: `1px solid ${BORDER}`,
                    borderRadius: 6,
                    background: 'white',
                  }}
                >
                  <Search size={14} color="#9CA3AF" />
                  <input
                    value={tableSearch}
                    onChange={e => setTableSearch(e.target.value)}
                    onKeyDown={e => {
                      if (e.key === 'Enter') void runView(1);
                    }}
                    placeholder="Search table"
                    style={{
                      border: 'none',
                      outline: 'none',
                      fontSize: '0.8125rem',
                      width: 160,
                      background: 'transparent',
                    }}
                  />
                </div>
                <button type="button" style={btnSecondary} onClick={() => void runView(1)}>
                  Search
                </button>
                <button
                  type="button"
                  style={btnSecondary}
                  disabled={exporting}
                  onClick={() => void onExport()}
                >
                  <Download size={14} />
                  {exporting ? 'Exporting' : 'Export Excel'}
                </button>
              </div>
            </div>

            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8125rem' }}>
                <thead>
                  <tr style={{ background: '#F9FAFB', borderBottom: `1px solid ${BORDER}` }}>
                    {['Customer Name', 'Product', 'Location', 'Quarter', 'Sales Quantity (MT)', 'Distributor'].map(
                      h => (
                        <th
                          key={h}
                          style={{
                            textAlign: 'left',
                            padding: '10px 12px',
                            fontSize: '0.6875rem',
                            fontWeight: 700,
                            color: '#6B7280',
                            textTransform: 'uppercase',
                            letterSpacing: '0.04em',
                          }}
                        >
                          {h}
                        </th>
                      ),
                    )}
                  </tr>
                </thead>
                <tbody>
                  {data.table.rows.length === 0 ? (
                    <tr>
                      <td colSpan={6} style={{ padding: 24, color: '#94A3B8', textAlign: 'center' }}>
                        No rows for the current filters.
                      </td>
                    </tr>
                  ) : (
                    data.table.rows.map((row, idx) => (
                      <tr
                        key={`${row.customer}-${row.product}-${row.location}-${idx}`}
                        style={{ borderBottom: `1px solid ${BORDER}` }}
                      >
                        <td style={{ padding: '10px 12px', color: '#374151' }}>{row.customer}</td>
                        <td style={{ padding: '10px 12px', color: '#374151' }}>{row.product}</td>
                        <td style={{ padding: '10px 12px', color: '#374151' }}>{row.location || 'Â'}</td>
                        <td style={{ padding: '10px 12px', color: '#6B7280' }}>
                          {formatPeriodDisplay(row.month)}
                        </td>
                        <td style={{ padding: '10px 12px', fontWeight: 600, color: BLUE }}>
                          {row.qty.toLocaleString()}
                        </td>
                        <td style={{ padding: '10px 12px', color: '#374151' }}>{row.distributor}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            <div
              style={{
                display: 'flex',
                justifyContent: 'flex-end',
                alignItems: 'center',
                gap: 10,
                marginTop: 14,
              }}
            >
              <span style={{ fontSize: '0.75rem', color: '#6B7280' }}>
                Page {page} of {totalPages}
              </span>
              <button
                type="button"
                style={btnSecondary}
                disabled={page <= 1 || loading}
                onClick={() => void runView(page - 1)}
              >
                Previous
              </button>
              <button
                type="button"
                style={btnSecondary}
                disabled={page >= totalPages || loading}
                onClick={() => void runView(page + 1)}
              >
                Next
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
