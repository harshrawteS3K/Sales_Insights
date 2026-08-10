/** APCOTEX reporting-quarter helpers (Q1=Apr–Jun … Q4=Jan–Mar). */

export type ParsedQuarter = {
  year: number;
  quarter: number;
  label: string;
};

const QUARTER_RANGE: Record<number, string> = {
  1: 'Apr–Jun',
  2: 'Jul–Sep',
  3: 'Oct–Dec',
  4: 'Jan–Mar',
};

const QUARTER_RE = /^\s*Q([1-4])\s+(\d{4})\s*$/i;

/** Parse `"Q2 2026"` → `{ year: 2026, quarter: 2, label: "Q2 2026" }`. */
export function parseQuarter(q: string): ParsedQuarter | null {
  const match = QUARTER_RE.exec((q || '').trim());
  if (!match) return null;
  const quarter = Number(match[1]);
  const year = Number(match[2]);
  return { year, quarter, label: `Q${quarter} ${year}` };
}

/** Human range for a quarter label or Q number. */
export function getQuarterRange(q: string | number): string {
  if (typeof q === 'number') {
    return QUARTER_RANGE[q] || '';
  }
  const parsed = parseQuarter(q);
  if (parsed) return QUARTER_RANGE[parsed.quarter] || '';
  const only = /^\s*Q([1-4])\s*$/i.exec(q || '');
  if (only) return QUARTER_RANGE[Number(only[1])] || '';
  return '';
}

export type TimelineReport = {
  reportId: number;
  reportingQuarter?: string | null;
  reportingMonth?: string | null;
  importedAt?: string | null;
  company?: string | null;
  distributor?: string | null;
  sales?: Array<{ quantity?: string | null }>;
  recordCount?: number;
};

export type QuarterBucket<T> = {
  label: string;
  year: number;
  quarter: number;
  range: string;
  reports: T[];
  distributorCount: number;
  totalQuantity: number;
};

export type YearBucket<T> = {
  year: number;
  quarters: QuarterBucket<T>[];
  reportCount: number;
};

function reportingLabelOf(report: TimelineReport): string {
  return (report.reportingQuarter || report.reportingMonth || '').trim();
}

/** Parse quantity display strings like `"1,234.50"` / `"10"`. */
export function parseQuantity(value: string | number | null | undefined): number {
  if (typeof value === 'number') return Number.isFinite(value) ? value : 0;
  if (!value) return 0;
  const cleaned = String(value).replace(/,/g, '').trim();
  const n = Number(cleaned);
  return Number.isFinite(n) ? n : 0;
}

export function sumReportQuantity(report: TimelineReport): number {
  if (!report.sales?.length) return 0;
  return report.sales.reduce((sum, line) => sum + parseQuantity(line.quantity), 0);
}

function importedSortKey(report: TimelineReport): number {
  if (!report.importedAt) return 0;
  const t = Date.parse(report.importedAt);
  return Number.isFinite(t) ? t : 0;
}

/**
 * Group reports into Year → Quarter → Distributor rows.
 * Sort: year desc, quarter desc (Q4→Q1), imported desc within quarter.
 */
export function buildYearQuarterTimeline<T extends TimelineReport>(
  reports: T[]
): YearBucket<T>[] {
  const byYear = new Map<number, Map<string, T[]>>();

  for (const report of reports) {
    const raw = reportingLabelOf(report);
    const parsed = parseQuarter(raw);
    const year = parsed?.year ?? 0;
    const label = parsed?.label ?? (raw || 'Unknown');
    if (!byYear.has(year)) byYear.set(year, new Map());
    const byQ = byYear.get(year)!;
    if (!byQ.has(label)) byQ.set(label, []);
    byQ.get(label)!.push(report);
  }

  const years = Array.from(byYear.keys()).sort((a, b) => b - a);
  return years.map(year => {
    const byQ = byYear.get(year)!;
    const quarterEntries = Array.from(byQ.entries()).map(([label, list]) => {
      const parsed = parseQuarter(label);
      const qNum = parsed?.quarter ?? 0;
      const sorted = [...list].sort((a, b) => importedSortKey(b) - importedSortKey(a));
      const companies = new Set(
        sorted.map(r => (r.company || r.distributor || '').trim().toLowerCase()).filter(Boolean)
      );
      const totalQuantity = sorted.reduce((s, r) => s + sumReportQuantity(r), 0);
      return {
        label,
        year: parsed?.year ?? year,
        quarter: qNum,
        range: getQuarterRange(qNum || label),
        reports: sorted,
        distributorCount: companies.size || sorted.length,
        totalQuantity,
      } satisfies QuarterBucket<T>;
    });

    quarterEntries.sort((a, b) => {
      if (a.quarter !== b.quarter) return b.quarter - a.quarter;
      return b.label.localeCompare(a.label);
    });

    return {
      year,
      quarters: quarterEntries,
      reportCount: quarterEntries.reduce((s, q) => s + q.reports.length, 0),
    };
  });
}

/** Flat overview rows newest-first for the summary strip. */
export function flattenQuarterOverview<T extends TimelineReport>(
  timeline: YearBucket<T>[]
): QuarterBucket<T>[] {
  return timeline.flatMap(y => y.quarters);
}

export function formatMt(qty: number): string {
  return qty.toLocaleString(undefined, {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  });
}
