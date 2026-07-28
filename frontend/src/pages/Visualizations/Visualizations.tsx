import { useState, useEffect } from 'react';
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
} from 'recharts';
import { Filter, BarChart3, Users } from 'lucide-react';
import { BLUE, BORDER, PRODUCT_COLORS, DIST_COLORS } from '../../constants/theme';
import { KpiCard } from '../../components/ui/KpiCard';
import { ChartCard } from '../../components/ui/ChartCard';
import type { TabKey, KpiItem } from '../../types';
import { VisualizationsService } from '../../services/visualizations.service';
import { ApiError } from '../../api';
import { StatusBanner } from '../../components/common/StatusBanner';

export function Visualizations() {
  const [tab, setTab] = useState<TabKey>('products');
  const [pFilters, setPFilters] = useState({ product: 'All', period: 'All' });
  const [dFilters, setDFilters] = useState({ distributor: 'All', period: 'All' });

  const [loaded, setLoaded] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [productsKpis, setProductsKpis] = useState<KpiItem[]>([]);
  const [distributorsKpis, setDistributorsKpis] = useState<KpiItem[]>([]);
  const [productMix, setProductMix] = useState<any[]>([]);
  const [productBarData, setProductBarData] = useState<any[]>([]);
  const [top10dist, setTop10dist] = useState<any[]>([]);
  const [distProductMix, setDistProductMix] = useState<any[]>([]);
  const [productOpts, setProductOpts] = useState<Record<string, string[]>>({ product: [], period: [] });
  const [distOpts, setDistOpts] = useState<Record<string, string[]>>({ distributor: [], period: [] });

  const periodParam = (period: string) => (period && period !== 'All' ? period : undefined);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [
        pKpis,
        dKpis,
        mixData,
        barData,
        topDist,
        distMix,
        pOpts,
        dOpts,
      ] = await Promise.all([
        VisualizationsService.getProductsKpi(),
        VisualizationsService.getDistributorsKpi(),
        VisualizationsService.getProductMix(),
        VisualizationsService.getProductBarData(),
        VisualizationsService.getTop10Distributors(),
        VisualizationsService.getDistProductMix(),
        VisualizationsService.getProductFilterOptions(),
        VisualizationsService.getDistributorFilterOptions(),
      ]);

      setProductsKpis(pKpis);
      setDistributorsKpis(dKpis);
      setProductMix(mixData);
      setProductBarData(barData);
      setTop10dist(topDist);
      setDistProductMix(distMix);
      setProductOpts({
        product: pOpts.product || [],
        period: pOpts.period || [],
      });
      setDistOpts({
        distributor: dOpts.distributor || [],
        period: dOpts.period || [],
      });

      const periods = (pOpts.period || []).filter(p => p !== 'All');
      if (periods.length > 0) {
        setPFilters(f => ({ ...f, period: periods[0] }));
        setDFilters(f => ({ ...f, period: periods[0] }));
      }

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
  }, []);

  useEffect(() => {
    if (!loaded) return;
    const period = periodParam(tab === 'products' ? pFilters.period : dFilters.period);
    let cancelled = false;
    (async () => {
      try {
        const [mixData, barData, topDist, distMix] = await Promise.all([
          VisualizationsService.getProductMix(period),
          VisualizationsService.getProductBarData(period),
          VisualizationsService.getTop10Distributors(period),
          VisualizationsService.getDistProductMix(period),
        ]);
        if (cancelled) return;
        setProductMix(mixData);
        setProductBarData(barData);
        setTop10dist(topDist);
        setDistProductMix(distMix);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : 'Failed to refresh charts');
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [pFilters.period, dFilters.period, tab, loaded]);

  const periodLabel =
    (tab === 'products' ? pFilters.period : dFilters.period) || 'All reporting months';

  return (
    <div style={{ padding: '28px 32px', fontFamily: "'Inter', system-ui, sans-serif", maxWidth: 1500 }}>
      <div style={{ marginBottom: 20 }}>
        <h1 style={{ fontSize: '1.375rem', fontWeight: 700, color: '#111827', margin: 0, marginBottom: 4 }}>
          Visualizations & Analytics
        </h1>
        <p style={{ fontSize: '0.875rem', color: '#6B7280', margin: 0 }}>
          Insights generated from consolidated distributor sales data — {periodLabel}
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
          {/* Tabs */}
          <div style={{ display: 'flex', gap: 4, marginBottom: 24, background: '#F3F4F6', padding: 4, borderRadius: 10, width: 'fit-content' }}>
            {[
              { key: 'products' as TabKey, label: 'Products', icon: BarChart3 },
              { key: 'distributors' as TabKey, label: 'Top Distributors', icon: Users },
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
                  transition: 'all 0.15s',
                }}
              >
                <Icon size={15} />
                {label}
              </button>
            ))}
          </div>

          {tab === 'products' && (
            <ProductsTab
              filters={pFilters}
              opts={productOpts}
              kpis={productsKpis}
              productMix={productMix}
              productBarData={productBarData}
              setFilter={(k, v) => setPFilters(f => ({ ...f, [k]: v }))}
            />
          )}
          {tab === 'distributors' && (
            <DistributorsTab
              filters={dFilters}
              opts={distOpts}
              kpis={distributorsKpis}
              top10dist={top10dist}
              distProductMix={distProductMix}
              setFilter={(k, v) => setDFilters(f => ({ ...f, [k]: v }))}
            />
          )}
        </>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════
   PRODUCTS TAB
   ═══════════════════════════════════════════ */
function ProductsTab({
  filters,
  opts,
  kpis,
  productMix,
  productBarData,
  setFilter,
}: {
  filters: any;
  opts: Record<string, string[]>;
  kpis: KpiItem[];
  productMix: any[];
  productBarData: any[];
  setFilter: (k: string, v: string) => void;
}) {
  return (
    <>
      <FilterBar
        opts={opts}
        filters={filters}
        setFilter={setFilter}
        onReset={() => {
          setFilter('product', 'All');
          setFilter('period', 'All');
        }}
      />

      {/* KPI row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, marginBottom: 20 }}>
        {kpis.map(kpi => (
          <KpiCard key={kpi.label} label={kpi.label} value={kpi.value} />
        ))}
      </div>

      {/* 2-column grid: pie + bar */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
        {/* Product Sales Mix — donut, Top 7 + Others */}
        <ChartCard title="Product Sales Mix" subtitle="Top 7 products + Others — share of total quantity">
          <ResponsiveContainer width="100%" height={280}>
            <PieChart>
              <Pie data={productMix} cx="42%" cy="50%" innerRadius={65} outerRadius={105} paddingAngle={2} dataKey="value" nameKey="name">
                {productMix.map((entry, i) => (
                  <Cell key={i} fill={entry.color} />
                ))}
              </Pie>
              <Tooltip formatter={v => `${v}%`} contentStyle={{ fontSize: 12, borderRadius: 8, border: `1px solid ${BORDER}` }} />
              <Legend
                layout="vertical"
                align="right"
                verticalAlign="middle"
                wrapperStyle={{ fontSize: 11, paddingLeft: 8 }}
                formatter={(value, entry: any) => <span style={{ color: '#374151' }}>{value} ({entry.payload.value}%)</span>}
              />
            </PieChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* Total Quantity — horizontal bar, Top 15 + Others */}
        <ChartCard title="Total Quantity by Product (kg)" subtitle="Quantity by product">
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={productBarData} layout="vertical" margin={{ top: 4, right: 28, left: 16, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#F3F4F6" horizontal={false} />
              <XAxis type="number" tick={{ fontSize: 10, fill: '#9CA3AF' }} axisLine={false} tickLine={false} />
              <YAxis type="category" dataKey="product" tick={{ fontSize: 10, fill: '#374151' }} axisLine={false} tickLine={false} width={130} />
              <Tooltip
                contentStyle={{ fontSize: 12, borderRadius: 8, border: `1px solid ${BORDER}` }}
                formatter={(v: number) => [`${v.toLocaleString()} kg`, 'Quantity']}
              />
              <Bar dataKey="qty" name="Quantity (kg)" radius={[0, 4, 4, 0]}>
                {productBarData.map((entry, i) => (
                  <Cell key={i} fill={entry.product === 'Others' ? '#D1D5DB' : PRODUCT_COLORS[i % PRODUCT_COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>
    </>
  );
}

/* ═══════════════════════════════════════════
   TOP DISTRIBUTORS TAB
   ═══════════════════════════════════════════ */
function DistributorsTab({
  filters,
  opts,
  kpis,
  top10dist,
  distProductMix,
  setFilter,
}: {
  filters: any;
  opts: Record<string, string[]>;
  kpis: KpiItem[];
  top10dist: any[];
  distProductMix: any[];
  setFilter: (k: string, v: string) => void;
}) {
  return (
    <>
      <FilterBar
        opts={opts}
        filters={filters}
        setFilter={setFilter}
        onReset={() => {
          setFilter('distributor', 'All');
          setFilter('period', 'All');
        }}
      />

      {/* KPI row — 5 cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 16, marginBottom: 20 }}>
        {kpis.map(kpi => (
          <KpiCard key={kpi.label} label={kpi.label} value={kpi.value} />
        ))}
      </div>

      {/* 2-column grid: total volume bar + product mix stacked bar */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
        {/* Total Volume by Distributor */}
        <ChartCard title="Total Volume by Distributor" subtitle="Total quantity dispatched">
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={top10dist} layout="vertical" margin={{ top: 4, right: 24, left: 8, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#F3F4F6" horizontal={false} />
              <XAxis type="number" tick={{ fontSize: 10, fill: '#9CA3AF' }} axisLine={false} tickLine={false} />
              <YAxis type="category" dataKey="name" tick={{ fontSize: 10, fill: '#374151' }} axisLine={false} tickLine={false} width={110} />
              <Tooltip
                contentStyle={{ fontSize: 12, borderRadius: 8, border: `1px solid ${BORDER}` }}
                formatter={(v: number) => [`${v.toLocaleString()} kg`, 'Quantity']}
              />
              <Bar dataKey="qty" name="Quantity (kg)" radius={[0, 4, 4, 0]}>
                {top10dist.map((_, i) => (
                  <Cell key={i} fill={DIST_COLORS[i % DIST_COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* Product Mix by Distributor — stacked */}
        <ChartCard title="Product Mix by Distributor" subtitle="Quantity breakdown per product">
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
                formatter={(v: number) => [`${v.toLocaleString()} kg`]}
              />
              <Legend wrapperStyle={{ fontSize: 11, paddingTop: 8 }} />
              {(['CB 300', 'CB 4600', 'CB 4400', 'CB 548'] as const).map((key, i) => (
                <Bar key={key} dataKey={key} stackId="a" fill={PRODUCT_COLORS[i]} radius={i === 3 ? [4, 4, 0, 0] : [0, 0, 0, 0]} />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>
    </>
  );
}

/* ═══════════════════════════════════════════
   FILTER BAR
   ═══════════════════════════════════════════ */
function FilterBar({
  opts,
  filters,
  setFilter,
  onReset,
}: {
  opts: Record<string, string[]>;
  filters: Record<string, string>;
  setFilter: (k: string, v: string) => void;
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
        alignItems: 'center',
        gap: 12,
        flexWrap: 'wrap',
        boxShadow: '0 1px 4px rgba(0,0,0,0.04)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: '#6B7280', fontSize: '0.8125rem', fontWeight: 600 }}>
        <Filter size={14} />
        Filters:
      </div>
      {Object.entries(opts).map(([key, options]) => (
        <select
          key={key}
          value={filters[key] || 'All'}
          onChange={e => setFilter(key, e.target.value)}
          style={{
            height: 32,
            padding: '0 10px',
            border: `1px solid ${BORDER}`,
            borderRadius: 6,
            fontSize: '0.8125rem',
            color: '#374151',
            background: 'white',
            cursor: 'pointer',
          }}
        >
          {options.map(o => (
            <option key={o} value={o}>
              {o === 'All'
                ? `All ${
                    key === 'period'
                      ? 'Reporting Months'
                      : key.charAt(0).toUpperCase() + key.slice(1) + 's'
                  }`
                : o}
            </option>
          ))}
        </select>
      ))}
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
        }}
      >
        Reset
      </button>
    </div>
  );
}
