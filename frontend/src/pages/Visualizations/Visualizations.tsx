import { useState, useEffect, useCallback } from 'react';
import {
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  LineChart,
  Line,
  Treemap,
} from 'recharts';
import { Filter, BarChart3, Users } from 'lucide-react';
import { BLUE, BORDER, PRODUCT_COLORS, DIST_COLORS } from '../../constants/theme';
import { KpiCard } from '../../components/ui/KpiCard';
import { ChartCard } from '../../components/ui/ChartCard';
import { SearchAutocomplete } from '../../components/ui/SearchAutocomplete';
import { SalesHeatmap } from '../../components/ui/SalesHeatmap';
import type { TabKey, KpiItem } from '../../types';
import { VisualizationsService } from '../../services/visualizations.service';
import { AuditTrailService } from '../../services/auditTrail.service';
import { ApiError } from '../../api';
import { StatusBanner } from '../../components/common/StatusBanner';

type VizFilters = {
  product: string;
  distributor: string;
  period: string;
};

const EMPTY_FILTERS: VizFilters = { product: 'All', distributor: 'All', period: 'All' };

export function Visualizations() {
  const [tab, setTab] = useState<TabKey>('products');
  const [filters, setFilters] = useState<VizFilters>({ ...EMPTY_FILTERS });
  const [topN, setTopN] = useState<10 | 20 | 50>(10);

  const [loaded, setLoaded] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [productsKpis, setProductsKpis] = useState<KpiItem[]>([]);
  const [distributorsKpis, setDistributorsKpis] = useState<KpiItem[]>([]);
  const [productMix, setProductMix] = useState<any[]>([]);
  const [productBarData, setProductBarData] = useState<any[]>([]);
  const [topDist, setTopDist] = useState<any[]>([]);
  const [distContribution, setDistContribution] = useState<any[]>([]);
  const [quarterlyTrend, setQuarterlyTrend] = useState<any[]>([]);
  const [heatmap, setHeatmap] = useState<{ months: string[]; distributors: string[]; cells: any[] }>({
    months: [],
    distributors: [],
    cells: [],
  });
  const [distProductMix, setDistProductMix] = useState<any[]>([]);
  const [productOpts, setProductOpts] = useState<string[]>([]);
  const [distOpts, setDistOpts] = useState<string[]>([]);
  const [periodOpts, setPeriodOpts] = useState<string[]>([]);

  const filterParams = useCallback(() => {
    const period = filters.period && filters.period !== 'All' ? filters.period : undefined;
    const product = filters.product && filters.product !== 'All' ? filters.product : undefined;
    const distributor =
      filters.distributor && filters.distributor !== 'All' ? filters.distributor : undefined;
    return { period, product, distributor };
  }, [filters]);

  const loadOptions = async () => {
    const [pOpts, dOpts] = await Promise.all([
      VisualizationsService.getProductFilterOptions(),
      VisualizationsService.getDistributorFilterOptions(),
    ]);
    const products = (pOpts.product || []).filter(p => p !== 'All');
    const distributors = (dOpts.distributor || []).filter(d => d !== 'All');
    const periods = (pOpts.period || dOpts.period || []).filter(p => p !== 'All');
    setProductOpts(products);
    setDistOpts(distributors);
    setPeriodOpts(periods);
    if (periods.length > 0) {
      setFilters(f => (f.period === 'All' ? { ...f, period: periods[0] } : f));
    }
  };

  const loadCharts = useCallback(async () => {
    const fp = filterParams();
    const [
      pKpis,
      dKpis,
      mixData,
      barData,
      top,
      contrib,
      trend,
      heat,
      distMix,
    ] = await Promise.all([
      VisualizationsService.getProductsKpi(fp),
      VisualizationsService.getDistributorsKpi(fp),
      VisualizationsService.getProductMix({ ...fp, top_n: Math.min(topN, 15) }),
      VisualizationsService.getProductBarData({ ...fp, top_n: topN }),
      VisualizationsService.getTop10Distributors({ ...fp, limit: 15 }),
      VisualizationsService.getDistributorContribution({ ...fp, top_n: 8 }),
      VisualizationsService.getQuarterlyTrend({ product: fp.product, distributor: fp.distributor }),
      VisualizationsService.getDistributorQuarterHeatmap({
        product: fp.product,
        distributor: fp.distributor,
        distributor_limit: 15,
      }),
      VisualizationsService.getDistProductMix(fp),
    ]);
    setProductsKpis(pKpis);
    setDistributorsKpis(dKpis);
    setProductMix(mixData);
    setProductBarData(barData);
    setTopDist(top);
    setDistContribution(contrib);
    setQuarterlyTrend(trend);
    setHeatmap(heat);
    setDistProductMix(distMix);
  }, [filterParams, topN]);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      await loadOptions();
      await loadCharts();
      setLoaded(true);
    } catch (err) {
      setLoaded(false);
      setError(err instanceof ApiError ? err.message : 'Failed to load visualization data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
    void AuditTrailService.recordEvent({
      action: 'Visualization Opened',
      module: 'Visualization',
      description: 'Opened Visualizations workspace',
      status: 'Info',
      entity_type: 'visualization',
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!loaded) return;
    let cancelled = false;
    (async () => {
      try {
        await loadCharts();
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : 'Failed to refresh charts');
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [filters, topN, tab, loaded, loadCharts]);

  const setFilter = (key: keyof VizFilters, value: string) => {
    setFilters(f => ({ ...f, [key]: value }));
  };

  const periodLabel = filters.period && filters.period !== 'All' ? filters.period : 'All reporting quarters';

  return (
    <div style={{ padding: '28px 32px', fontFamily: "'Inter', system-ui, sans-serif", maxWidth: 1500 }}>
      <div style={{ marginBottom: 20 }}>
        <h1 style={{ fontSize: '1.375rem', fontWeight: 700, color: '#111827', margin: 0, marginBottom: 4 }}>
          Visualizations & Analytics
        </h1>
        <p style={{ fontSize: '0.875rem', color: '#6B7280', margin: 0 }}>
          Active reports only — {periodLabel}
        </p>
      </div>

      <StatusBanner
        loading={loading && !loaded}
        error={error}
        onRetry={loadData}
        loadingText="Loading visualizations…"
      />

      {loaded && (
        <>
          <div
            style={{
              display: 'flex',
              gap: 4,
              marginBottom: 24,
              background: '#F3F4F6',
              padding: 4,
              borderRadius: 10,
              width: 'fit-content',
            }}
          >
            {[
              { key: 'products' as TabKey, label: 'Products', icon: BarChart3 },
              { key: 'distributors' as TabKey, label: 'Distributors', icon: Users },
            ].map(({ key, label, icon: Icon }) => (
              <button
                key={key}
                onClick={() => setTab(key)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 7,
                  padding: '8px 20px',
                  borderRadius: 7,
                  border: 'none',
                  background: tab === key ? 'white' : 'transparent',
                  color: tab === key ? BLUE : '#6B7280',
                  fontWeight: tab === key ? 700 : 500,
                  fontSize: '0.875rem',
                  cursor: 'pointer',
                  boxShadow: tab === key ? '0 1px 4px rgba(0,0,0,0.08)' : 'none',
                }}
              >
                <Icon size={15} />
                {label}
              </button>
            ))}
          </div>

          <FilterBar
            productOpts={productOpts}
            distOpts={distOpts}
            periodOpts={periodOpts}
            filters={filters}
            topN={topN}
            showTopN={tab === 'products'}
            setFilter={setFilter}
            setTopN={setTopN}
            onReset={() => setFilters({ ...EMPTY_FILTERS, period: periodOpts[0] || 'All' })}
          />

          {tab === 'products' && (
            <ProductsTab
              kpis={productsKpis}
              productMix={productMix}
              productBarData={productBarData}
              quarterlyTrend={quarterlyTrend}
              topN={topN}
            />
          )}
          {tab === 'distributors' && (
            <DistributorsTab
              kpis={distributorsKpis}
              topDist={topDist}
              distContribution={distContribution}
              distProductMix={distProductMix}
              heatmap={heatmap}
              quarterlyTrend={quarterlyTrend}
            />
          )}
        </>
      )}
    </div>
  );
}

function ProductsTab({
  kpis,
  productMix,
  productBarData,
  quarterlyTrend,
  topN,
}: {
  kpis: KpiItem[];
  productMix: any[];
  productBarData: any[];
  quarterlyTrend: any[];
  topN: number;
}) {
  const treemapData = productMix.map(d => ({
    name: d.name,
    size: d.qty ?? d.value,
    fill: d.color,
  }));
  const trendKey = quarterlyTrend.some(d => d.quarter) ? 'quarter' : 'month';

  return (
    <>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, marginBottom: 20 }}>
        {kpis.map(kpi => (
          <KpiCard key={kpi.label} label={kpi.label} value={kpi.value} />
        ))}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 20, marginBottom: 20 }}>
        <ChartCard title="Quarterly Sales Trend" subtitle="Total quantity (MT) by reporting quarter — line chart">
          {quarterlyTrend.length === 0 ? (
            <EmptyChart />
          ) : (
            <ResponsiveContainer width="100%" height={260}>
              <LineChart data={quarterlyTrend} margin={{ top: 8, right: 24, left: 8, bottom: 8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#F3F4F6" />
                <XAxis dataKey={trendKey} tick={{ fontSize: 10, fill: '#9CA3AF' }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 10, fill: '#9CA3AF' }} axisLine={false} tickLine={false} />
                <Tooltip
                  contentStyle={{ fontSize: 12, borderRadius: 8, border: `1px solid ${BORDER}` }}
                  formatter={(v: number) => [`${Number(v).toLocaleString()} MT`, 'Quantity']}
                />
                <Line type="monotone" dataKey="qty" stroke={BLUE} strokeWidth={2.5} dot={{ r: 3 }} name="Quantity (MT)" />
              </LineChart>
            </ResponsiveContainer>
          )}
        </ChartCard>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 20 }}>
        <ChartCard title="Top Products" subtitle={`Top ${topN} by quantity + Others`}>
          {productBarData.length === 0 ? (
            <EmptyChart />
          ) : (
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={productBarData} margin={{ top: 8, right: 16, left: 0, bottom: 48 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#F3F4F6" vertical={false} />
                <XAxis
                  dataKey="product"
                  tick={{ fontSize: 10, fill: '#9CA3AF' }}
                  axisLine={false}
                  tickLine={false}
                  angle={-28}
                  textAnchor="end"
                  interval={0}
                  height={60}
                />
                <YAxis tick={{ fontSize: 10, fill: '#9CA3AF' }} axisLine={false} tickLine={false} />
                <Tooltip
                  contentStyle={{ fontSize: 12, borderRadius: 8, border: `1px solid ${BORDER}` }}
                  formatter={(v: number) => [`${Number(v).toLocaleString()} MT`, 'Quantity']}
                />
                <Bar dataKey="qty" name="Quantity (MT)" radius={[4, 4, 0, 0]}>
                  {productBarData.map((entry, i) => (
                    <Cell
                      key={i}
                      fill={entry.product === 'Others' ? '#D1D5DB' : PRODUCT_COLORS[i % PRODUCT_COLORS.length]}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </ChartCard>

        <ChartCard title="Product Mix" subtitle="Treemap — contribution by quantity (ACTIVE reports)">
          {treemapData.length === 0 ? (
            <EmptyChart />
          ) : (
            <ResponsiveContainer width="100%" height={300}>
              <Treemap
                data={treemapData}
                dataKey="size"
                nameKey="name"
                stroke="#fff"
                content={<TreemapContent />}
              />
            </ResponsiveContainer>
          )}
        </ChartCard>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 20 }}>
        <ChartCard title="Product Mix (share %)" subtitle="Donut fallback view — Top products + Others">
          {productMix.length === 0 ? (
            <EmptyChart />
          ) : (
            <ResponsiveContainer width="100%" height={280}>
              <PieChart>
                <Pie
                  data={productMix}
                  cx="42%"
                  cy="50%"
                  innerRadius={65}
                  outerRadius={105}
                  paddingAngle={2}
                  dataKey="value"
                  nameKey="name"
                >
                  {productMix.map((entry, i) => (
                    <Cell key={i} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip
                  formatter={(v: number) => `${v}%`}
                  contentStyle={{ fontSize: 12, borderRadius: 8, border: `1px solid ${BORDER}` }}
                />
                <Legend
                  layout="vertical"
                  align="right"
                  verticalAlign="middle"
                  wrapperStyle={{ fontSize: 11, paddingLeft: 8 }}
                  formatter={(value, entry: any) => (
                    <span style={{ color: '#374151' }}>
                      {value} ({entry.payload.value}%)
                    </span>
                  )}
                />
              </PieChart>
            </ResponsiveContainer>
          )}
        </ChartCard>
      </div>
    </>
  );
}

function DistributorsTab({
  kpis,
  topDist,
  distContribution,
  distProductMix,
  heatmap,
  quarterlyTrend,
}: {
  kpis: KpiItem[];
  topDist: any[];
  distContribution: any[];
  distProductMix: any[];
  heatmap: { months: string[]; distributors: string[]; cells: any[] };
  quarterlyTrend: any[];
}) {
  const stackKeys = (() => {
    const keys = new Set<string>();
    for (const row of distProductMix) {
      Object.keys(row).forEach(k => {
        if (k !== 'distributor') keys.add(k);
      });
    }
    return Array.from(keys).slice(0, 8);
  })();
  const trendKey = quarterlyTrend.some(d => d.quarter) ? 'quarter' : 'month';

  return (
    <>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 16, marginBottom: 20 }}>
        {kpis.map(kpi => (
          <KpiCard key={kpi.label} label={kpi.label} value={kpi.value} />
        ))}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 20, marginBottom: 20 }}>
        <ChartCard title="Quarterly Sales Trend" subtitle="Quantity by quarter (filtered)">
          {quarterlyTrend.length === 0 ? (
            <EmptyChart />
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={quarterlyTrend} margin={{ top: 8, right: 24, left: 8, bottom: 8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#F3F4F6" />
                <XAxis dataKey={trendKey} tick={{ fontSize: 10, fill: '#9CA3AF' }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 10, fill: '#9CA3AF' }} axisLine={false} tickLine={false} />
                <Tooltip
                  contentStyle={{ fontSize: 12, borderRadius: 8, border: `1px solid ${BORDER}` }}
                  formatter={(v: number) => [`${Number(v).toLocaleString()} MT`, 'Quantity']}
                />
                <Line type="monotone" dataKey="qty" stroke={BLUE} strokeWidth={2.5} dot={{ r: 3 }} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </ChartCard>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 20 }}>
        <ChartCard title="Sales by Distributor Company" subtitle="Horizontal bar — sorted descending">
          {topDist.length === 0 ? (
            <EmptyChart />
          ) : (
            <ResponsiveContainer width="100%" height={320}>
              <BarChart data={topDist} layout="vertical" margin={{ top: 4, right: 24, left: 8, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#F3F4F6" horizontal={false} />
                <XAxis type="number" tick={{ fontSize: 10, fill: '#9CA3AF' }} axisLine={false} tickLine={false} />
                <YAxis
                  type="category"
                  dataKey="name"
                  tick={{ fontSize: 10, fill: '#374151' }}
                  axisLine={false}
                  tickLine={false}
                  width={120}
                />
                <Tooltip
                  contentStyle={{ fontSize: 12, borderRadius: 8, border: `1px solid ${BORDER}` }}
                  formatter={(v: number) => [`${Number(v).toLocaleString()} MT`, 'Quantity']}
                />
                <Bar dataKey="qty" name="Quantity (MT)" radius={[0, 4, 4, 0]}>
                  {topDist.map((_, i) => (
                    <Cell key={i} fill={DIST_COLORS[i % DIST_COLORS.length]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </ChartCard>

        <ChartCard title="Distributor Company Contribution" subtitle="Donut — % share of total quantity">
          {distContribution.length === 0 ? (
            <EmptyChart />
          ) : (
            <ResponsiveContainer width="100%" height={320}>
              <PieChart>
                <Pie
                  data={distContribution}
                  cx="42%"
                  cy="50%"
                  innerRadius={70}
                  outerRadius={110}
                  paddingAngle={2}
                  dataKey="value"
                  nameKey="name"
                >
                  {distContribution.map((entry, i) => (
                    <Cell key={i} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip
                  formatter={(v: number, _n, props: any) => [
                    `${v}% (${Number(props?.payload?.qty || 0).toLocaleString()} MT)`,
                    'Share',
                  ]}
                  contentStyle={{ fontSize: 12, borderRadius: 8, border: `1px solid ${BORDER}` }}
                />
                <Legend
                  layout="vertical"
                  align="right"
                  verticalAlign="middle"
                  wrapperStyle={{ fontSize: 11 }}
                  formatter={(value, entry: any) => (
                    <span style={{ color: '#374151' }}>
                      {value} ({entry.payload.value}%)
                    </span>
                  )}
                />
              </PieChart>
            </ResponsiveContainer>
          )}
        </ChartCard>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 20, marginBottom: 20 }}>
        <ChartCard title="Distributor vs Quarter" subtitle="Heatmap — quantity intensity (Top Distributor Companies)">
          <SalesHeatmap data={heatmap} height={360} />
        </ChartCard>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 20 }}>
        <ChartCard title="Product Mix by Distributor Company" subtitle="Stacked bar fallback">
          {distProductMix.length === 0 ? (
            <EmptyChart />
          ) : (
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={distProductMix} margin={{ top: 8, right: 16, left: 0, bottom: 40 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#F3F4F6" vertical={false} />
                <XAxis
                  dataKey="distributor"
                  tick={{ fontSize: 10, fill: '#9CA3AF' }}
                  axisLine={false}
                  tickLine={false}
                  angle={-30}
                  textAnchor="end"
                  interval={0}
                />
                <YAxis tick={{ fontSize: 10, fill: '#9CA3AF' }} axisLine={false} tickLine={false} />
                <Tooltip
                  contentStyle={{ fontSize: 12, borderRadius: 8, border: `1px solid ${BORDER}` }}
                  formatter={(v: number) => [`${Number(v).toLocaleString()} MT`]}
                />
                <Legend wrapperStyle={{ fontSize: 11, paddingTop: 8 }} />
                {stackKeys.map((key, i) => (
                  <Bar
                    key={key}
                    dataKey={key}
                    stackId="a"
                    fill={PRODUCT_COLORS[i % PRODUCT_COLORS.length]}
                    radius={i === stackKeys.length - 1 ? [4, 4, 0, 0] : [0, 0, 0, 0]}
                  />
                ))}
              </BarChart>
            </ResponsiveContainer>
          )}
        </ChartCard>
      </div>
    </>
  );
}

function FilterBar({
  productOpts,
  distOpts,
  periodOpts,
  filters,
  topN,
  showTopN,
  setFilter,
  setTopN,
  onReset,
}: {
  productOpts: string[];
  distOpts: string[];
  periodOpts: string[];
  filters: VizFilters;
  topN: 10 | 20 | 50;
  showTopN: boolean;
  setFilter: (k: keyof VizFilters, v: string) => void;
  setTopN: (n: 10 | 20 | 50) => void;
  onReset: () => void;
}) {
  return (
    <div
      style={{
        background: 'white',
        border: `1px solid ${BORDER}`,
        borderRadius: 10,
        padding: '13px 20px',
        marginBottom: 20,
        display: 'flex',
        alignItems: 'flex-end',
        gap: 14,
        flexWrap: 'wrap',
        boxShadow: '0 1px 4px rgba(0,0,0,0.04)',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          color: '#6B7280',
          fontSize: '0.8125rem',
          fontWeight: 600,
          paddingBottom: 6,
        }}
      >
        <Filter size={14} />
        Filters:
      </div>

      <SearchAutocomplete
        label="Distributor Company"
        options={distOpts}
        value={filters.distributor}
        onChange={v => setFilter('distributor', v)}
        placeholder="Search distributor…"
      />
      <SearchAutocomplete
        label="Product"
        options={productOpts}
        value={filters.product}
        onChange={v => setFilter('product', v)}
        placeholder="Search product…"
      />

      <div style={{ minWidth: 160 }}>
        <div style={{ fontSize: '0.65rem', color: '#6B7280', fontWeight: 600, marginBottom: 3 }}>
          Reporting Quarter
        </div>
        <select
          value={filters.period || 'All'}
          onChange={e => setFilter('period', e.target.value)}
          style={{
            height: 32,
            width: '100%',
            padding: '0 10px',
            border: `1px solid ${BORDER}`,
            borderRadius: 6,
            fontSize: '0.8125rem',
            color: '#374151',
            background: 'white',
            cursor: 'pointer',
          }}
        >
          <option value="All">All Reporting Quarters</option>
          {periodOpts.map(o => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
        </select>
      </div>

      {showTopN && (
        <div style={{ minWidth: 120 }}>
          <div style={{ fontSize: '0.65rem', color: '#6B7280', fontWeight: 600, marginBottom: 3 }}>
            Top Products
          </div>
          <select
            value={topN}
            onChange={e => setTopN(Number(e.target.value) as 10 | 20 | 50)}
            style={{
              height: 32,
              width: '100%',
              padding: '0 10px',
              border: `1px solid ${BORDER}`,
              borderRadius: 6,
              fontSize: '0.8125rem',
              color: '#374151',
              background: 'white',
              cursor: 'pointer',
            }}
          >
            <option value={10}>Top 10</option>
            <option value={20}>Top 20</option>
            <option value={50}>Top 50</option>
          </select>
        </div>
      )}

      <button
        onClick={onReset}
        style={{
          marginLeft: 'auto',
          padding: '0 14px',
          height: 32,
          background: 'none',
          border: `1px solid ${BORDER}`,
          borderRadius: 6,
          fontSize: '0.8125rem',
          color: '#6B7280',
          cursor: 'pointer',
          marginBottom: 0,
        }}
      >
        Reset
      </button>
    </div>
  );
}

function EmptyChart() {
  return (
    <div style={{ height: 200, display: 'grid', placeItems: 'center', color: '#9CA3AF', fontSize: 13 }}>
      No data for current filters
    </div>
  );
}

/** Custom treemap cell renderer (recharts). */
function TreemapContent(props: any) {
  const { x, y, width, height, name, fill } = props;
  if (width < 4 || height < 4) return null;
  return (
    <g>
      <rect x={x} y={y} width={width} height={height} style={{ fill: fill || BLUE, stroke: '#fff' }} />
      {width > 48 && height > 22 && (
        <text x={x + 6} y={y + 16} fill="#111827" fontSize={11} fontWeight={600}>
          {String(name || '').slice(0, Math.max(4, Math.floor(width / 7)))}
        </text>
      )}
    </g>
  );
}
