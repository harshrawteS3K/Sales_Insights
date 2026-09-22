import type { CSSProperties } from 'react';
import { Eye } from 'lucide-react';
import { SearchAutocomplete } from '../ui/SearchAutocomplete';
import { BLUE, BORDER } from '../../constants/theme';
import {
  PERIOD_OPTIONS,
  FY_OPTIONS,
  customMonthOptions,
  fyOptionLabel,
  isCustomPeriod,
  isFiscalYearEnabled,
  isRollingPeriod,
  type AnalyticsPeriod,
  type EnterpriseFilterOptions,
  type EnterpriseFilterState,
} from '../../utils/analyticsFilters';

const selectStyle: CSSProperties = {
  height: 32,
  minWidth: 160,
  padding: '0 10px',
  border: `1px solid ${BORDER}`,
  borderRadius: 6,
  fontSize: '0.8125rem',
  color: '#374151',
  background: 'white',
};

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

const labelStyle: CSSProperties = {
  fontSize: '0.65rem',
  color: '#6B7280',
  fontWeight: 600,
  marginBottom: 3,
};

type Props = {
  title?: string;
  actionLabel?: string;
  loading?: boolean;
  value: EnterpriseFilterState;
  options: EnterpriseFilterOptions;
  onChange: (patch: Partial<EnterpriseFilterState>) => void;
  onSubmit: () => void;
};

/**
 * Shared enterprise filter bar for Visualizations & Distributor Performance.
 * Order: Period → FY (conditional) → Segment → Distributor → Location → Customer → Product → Action
 */
export function EnterpriseAnalyticsFilters({
  title = 'Filters',
  actionLabel = 'View',
  loading = false,
  value,
  options,
  onChange,
  onSubmit,
}: Props) {
  const fyEnabled = isFiscalYearEnabled(value.period);
  const rolling = isRollingPeriod(value.period);
  const custom = isCustomPeriod(value.period);
  const monthOpts = customMonthOptions();
  const fyOptions =
    options.financial_years?.length
      ? options.financial_years
      : FY_OPTIONS.map(y => ({ value: y, label: fyOptionLabel(y) }));

  const onPeriodChange = (next: AnalyticsPeriod) => {
    const patch: Partial<EnterpriseFilterState> = { period: next };
    if (isCustomPeriod(next)) {
      // hide FY; keep months as-is
    } else if (isRollingPeriod(next)) {
      patch.startMonth = '';
      patch.endMonth = '';
    } else {
      patch.startMonth = '';
      patch.endMonth = '';
    }
    onChange(patch);
  };

  const onDistributorChange = (name: string) => {
    if (!name || name === 'All') {
      onChange({ distributorLabel: 'All', distributorId: null });
      return;
    }
    const hit = options.distributors.find(d => d.name === name);
    onChange({ distributorLabel: name, distributorId: hit?.id ?? null });
  };

  return (
    <div
      style={{
        background: 'white',
        border: `1px solid ${BORDER}`,
        borderRadius: 12,
        padding: '18px 20px',
        marginBottom: 20,
        boxShadow: '0 1px 4px rgba(0,0,0,0.04)',
      }}
    >
      <div style={{ fontSize: '0.8125rem', fontWeight: 700, color: '#0F172A', marginBottom: 12 }}>
        {title}
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'flex-end' }}>
        {/* 1. Period (primary) */}
        <div>
          <div style={labelStyle}>Period</div>
          <select
            value={value.period}
            onChange={e => onPeriodChange(e.target.value as AnalyticsPeriod)}
            style={{ ...selectStyle, minWidth: 180 }}
          >
            {PERIOD_OPTIONS.map(o => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>

        {/* 2. Financial Year — enabled for Full FY / Q; disabled for rolling; hidden for custom */}
        {!custom && (
          <div>
            <div style={labelStyle}>Financial Year</div>
            {rolling ? (
              <select
                disabled
                value=""
                style={{
                  ...selectStyle,
                  minWidth: 160,
                  color: '#9CA3AF',
                  background: '#F9FAFB',
                  cursor: 'not-allowed',
                }}
              >
                <option value="">Auto (Rolling Period)</option>
              </select>
            ) : (
              <select
                value={value.fiscalYearStart}
                disabled={!fyEnabled}
                onChange={e => onChange({ fiscalYearStart: Number(e.target.value) })}
                style={{
                  ...selectStyle,
                  minWidth: 140,
                  ...(fyEnabled
                    ? {}
                    : { color: '#9CA3AF', background: '#F9FAFB', cursor: 'not-allowed' }),
                }}
              >
                {fyOptions.map(y => (
                  <option key={y.value} value={y.value}>
                    {y.label}
                  </option>
                ))}
              </select>
            )}
          </div>
        )}

        {/* Custom From / To Month */}
        {custom && (
          <>
            <div>
              <div style={labelStyle}>From Month</div>
              <select
                value={value.startMonth}
                onChange={e => onChange({ startMonth: e.target.value })}
                style={{ ...selectStyle, minWidth: 140 }}
              >
                <option value="">Select…</option>
                {monthOpts.map(m => (
                  <option key={`from-${m.value}`} value={m.value}>
                    {m.label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <div style={labelStyle}>To Month</div>
              <select
                value={value.endMonth}
                onChange={e => onChange({ endMonth: e.target.value })}
                style={{ ...selectStyle, minWidth: 140 }}
              >
                <option value="">Select…</option>
                {monthOpts.map(m => (
                  <option key={`to-${m.value}`} value={m.value}>
                    {m.label}
                  </option>
                ))}
              </select>
            </div>
          </>
        )}

        {/* 3–7. Dimension filters */}
        <SearchAutocomplete
          label="Segment"
          options={options.segments}
          value={value.segment}
          onChange={v => onChange({ segment: v })}
          width={150}
        />
        <SearchAutocomplete
          label="Distributor"
          options={options.distributors.map(d => d.name)}
          value={value.distributorLabel}
          onChange={onDistributorChange}
          width={200}
        />
        <SearchAutocomplete
          label="Location"
          options={options.locations}
          value={value.location}
          onChange={v => onChange({ location: v })}
          width={140}
        />
        <SearchAutocomplete
          label="Customer"
          options={options.customers}
          value={value.customer}
          onChange={v => onChange({ customer: v })}
          width={200}
        />
        <SearchAutocomplete
          label="Product"
          options={options.products}
          value={value.product}
          onChange={v => onChange({ product: v })}
          width={170}
        />

        <button
          type="button"
          style={{ ...btnPrimary, opacity: loading ? 0.7 : 1 }}
          disabled={loading}
          onClick={onSubmit}
        >
          <Eye size={14} />
          {loading ? 'Loading…' : actionLabel}
        </button>
      </div>
    </div>
  );
}
