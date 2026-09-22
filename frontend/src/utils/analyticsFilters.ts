/** Shared enterprise analytics filter types & helpers (Visualizations + Distributor Performance). */

import { fyShortDisplay } from './quarter';

export type AnalyticsPeriod =
  | 'full_year'
  | 'q1'
  | 'q2'
  | 'q3'
  | 'q4'
  | 'last_3_months'
  | 'last_6_months'
  | 'last_12_months'
  | 'custom';

export const FY_OPTIONS = [2024, 2025, 2026] as const;

export const PERIOD_OPTIONS: Array<{ value: AnalyticsPeriod; label: string }> = [
  { value: 'full_year', label: 'Full Financial Year' },
  { value: 'q1', label: 'Q1 (Apr–Jun)' },
  { value: 'q2', label: 'Q2 (Jul–Sep)' },
  { value: 'q3', label: 'Q3 (Oct–Dec)' },
  { value: 'q4', label: 'Q4 (Jan–Mar)' },
  { value: 'last_3_months', label: 'Last 3 Months' },
  { value: 'last_6_months', label: 'Last 6 Months' },
  { value: 'last_12_months', label: 'Last 12 Months' },
  { value: 'custom', label: 'Custom Range' },
];

const MONTH_SHORT = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

export type EnterpriseFilterState = {
  period: AnalyticsPeriod;
  fiscalYearStart: number;
  segment: string;
  distributorId: number | null;
  distributorLabel: string;
  location: string;
  customer: string;
  product: string;
  startMonth: string;
  endMonth: string;
};

export type EnterpriseFilterOptions = {
  distributors: Array<{ id: number; name: string }>;
  segments: string[];
  locations: string[];
  customers: string[];
  products: string[];
  financial_years?: Array<{ value: number; label: string }>;
};

export function currentFyStart(): number {
  const now = new Date();
  const y = now.getFullYear();
  const start = now.getMonth() + 1 >= 4 ? y : y - 1;
  if ((FY_OPTIONS as readonly number[]).includes(start)) return start;
  return 2025;
}

export function defaultEnterpriseFilters(): EnterpriseFilterState {
  return {
    period: 'full_year',
    fiscalYearStart: currentFyStart(),
    segment: 'All',
    distributorId: null,
    distributorLabel: 'All',
    location: 'All',
    customer: 'All',
    product: 'All',
    startMonth: '',
    endMonth: '',
  };
}

/** FY is selectable only for Full FY and Q1–Q4. */
export function isFiscalYearEnabled(period: AnalyticsPeriod): boolean {
  return period === 'full_year' || period === 'q1' || period === 'q2' || period === 'q3' || period === 'q4';
}

export function isRollingPeriod(period: AnalyticsPeriod): boolean {
  return period === 'last_3_months' || period === 'last_6_months' || period === 'last_12_months';
}

export function isCustomPeriod(period: AnalyticsPeriod): boolean {
  return period === 'custom';
}

/** Month+Year options spanning several Indian FYs for Custom Range. */
export function customMonthOptions(): Array<{ value: string; label: string }> {
  const startFy = currentFyStart() - 2;
  const out: Array<{ value: string; label: string }> = [];
  for (let fy = startFy; fy <= startFy + 4; fy++) {
    for (let m = 4; m <= 12; m++) {
      out.push({
        value: `${fy}-${String(m).padStart(2, '0')}`,
        label: `${MONTH_SHORT[m - 1]} ${fy}`,
      });
    }
    const endYear = fy + 1;
    for (let m = 1; m <= 3; m++) {
      out.push({
        value: `${endYear}-${String(m).padStart(2, '0')}`,
        label: `${MONTH_SHORT[m - 1]} ${endYear}`,
      });
    }
  }
  return out;
}

export function fyOptionLabel(fyStart: number): string {
  return fyShortDisplay(fyStart);
}

/** Display label for a selected FY + quarter period (never calendar Q4 2025). */
export function selectedPeriodDisplay(period: AnalyticsPeriod, fyStart: number): string {
  const fy = fyShortDisplay(fyStart);
  switch (period) {
    case 'full_year':
      return fy;
    case 'q1':
      return `${fy} • Q1 (Apr–Jun)`;
    case 'q2':
      return `${fy} • Q2 (Jul–Sep)`;
    case 'q3':
      return `${fy} • Q3 (Oct–Dec)`;
    case 'q4':
      return `${fy} • Q4 (Jan–Mar)`;
    case 'last_3_months':
      return 'Last 3 Months (Rolling)';
    case 'last_6_months':
      return 'Last 6 Months (Rolling)';
    case 'last_12_months':
      return 'Last 12 Months (Rolling)';
    case 'custom':
      return 'Custom Range';
    default:
      return fy;
  }
}

export function toAnalyticsQuery(state: EnterpriseFilterState) {
  const rolling = isRollingPeriod(state.period);
  const custom = isCustomPeriod(state.period);
  return {
    distributor_id: state.distributorId,
    customer: state.customer !== 'All' ? state.customer : null,
    product: state.product !== 'All' ? state.product : null,
    location: state.location !== 'All' ? state.location : null,
    segment: state.segment !== 'All' ? state.segment : null,
    fiscal_year_start: rolling || custom ? null : state.fiscalYearStart,
    period: state.period,
    start_month: custom ? state.startMonth || null : null,
    end_month: custom ? state.endMonth || null : null,
  };
}

export function validateEnterpriseFilters(state: EnterpriseFilterState): string | null {
  if (isCustomPeriod(state.period) && (!state.startMonth || !state.endMonth)) {
    return 'Select From Month and To Month for a custom range.';
  }
  return null;
}
