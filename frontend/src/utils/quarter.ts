/** Indian Financial Year helpers (Apr–Mar).

Canonical label:  `FY 2025-26 • Q1`
Display label:    `FY 2025–26 • Q1 (Apr–Jun)`

| Display             | Months              |
| ------------------- | ------------------- |
| FY 2025–26 • Q1     | Apr 2025 – Jun 2025 |
| FY 2025–26 • Q2     | Jul 2025 – Sep 2025 |
| FY 2025–26 • Q3     | Oct 2025 – Dec 2025 |
| FY 2025–26 • Q4     | Jan 2026 – Mar 2026 |
*/

export type ParsedQuarter = {
  /** FY start year (e.g. 2025 for FY 2025–26). */
  year: number;
  quarter: number;
  /** Canonical storage label. */
  label: string;
  kind?: 'quarter' | 'year';
};

const QUARTER_RANGE: Record<number, string> = {
  1: 'Apr–Jun',
  2: 'Jul–Sep',
  3: 'Oct–Dec',
  4: 'Jan–Mar',
};

const FY_QUARTER_RE =
  /^\s*FY\s*(\d{4})\s*[-–—/]\s*(\d{2}|\d{4})\s*[•·.\-]?\s*Q\s*([1-4])\s*$/i;
const FY_ANNUAL_RE = /^\s*FY\s*(\d{4})\s*[-–—/]\s*(\d{2}|\d{4})\s*$/i;
const LEGACY_Q_RE = /^\s*Q([1-4])\s+(\d{4})\s*$/i;
const SUBJECT_Q_FY_RE =
  /^\s*Q\s*([1-4])\s+FY\s*(\d{4})\s*[-–—/]\s*(\d{2}|\d{4})\s*$/i;
const RANGE_PAREN_RE = /\s*\((?:Apr|Jul|Oct|Jan)[^)]*\)\s*$/i;
const MONTH_LABEL_RE =
  /^\s*(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})\s*$/i;
const MONTH_INDEX: Record<string, number> = {
  january: 1, february: 2, march: 3, april: 4, may: 5, june: 6,
  july: 7, august: 8, september: 9, october: 10, november: 11, december: 12,
};

function fyEndOk(start: number, endRaw: string): boolean {
  const expectedYy = String((start + 1) % 100).padStart(2, '0');
  if (endRaw.length === 2) return endRaw === expectedYy;
  if (endRaw.length === 4 && /^\d{4}$/.test(endRaw)) return Number(endRaw) === start + 1;
  return false;
}

export function fyShort(fyStart: number): string {
  return `FY ${fyStart}-${String((fyStart + 1) % 100).padStart(2, '0')}`;
}

export function fyShortDisplay(fyStart: number): string {
  return `FY ${fyStart}–${String((fyStart + 1) % 100).padStart(2, '0')}`;
}

export function fyQuarterLabel(fyStart: number, quarter: number): string {
  return `${fyShort(fyStart)} • Q${quarter}`;
}

/** Parse FY / legacy quarter labels into `{ year: fyStart, quarter, label }`. */
export function parseQuarter(q: string): ParsedQuarter | null {
  let text = (q || '').trim();
  if (!text) return null;
  text = text.replace(RANGE_PAREN_RE, '').trim();

  let m = FY_QUARTER_RE.exec(text);
  if (m && fyEndOk(Number(m[1]), m[2])) {
    const year = Number(m[1]);
    const quarter = Number(m[3]);
    return { year, quarter, label: fyQuarterLabel(year, quarter), kind: 'quarter' };
  }

  m = SUBJECT_Q_FY_RE.exec(text);
  if (m && fyEndOk(Number(m[2]), m[3])) {
    const year = Number(m[2]);
    const quarter = Number(m[1]);
    return { year, quarter, label: fyQuarterLabel(year, quarter), kind: 'quarter' };
  }

  m = FY_ANNUAL_RE.exec(text);
  if (m && fyEndOk(Number(m[1]), m[2])) {
    const year = Number(m[1]);
    return { year, quarter: 0, label: fyShort(year), kind: 'year' };
  }

  m = LEGACY_Q_RE.exec(text);
  if (m) {
    const quarter = Number(m[1]);
    const year = Number(m[2]);
    return { year, quarter, label: fyQuarterLabel(year, quarter), kind: 'quarter' };
  }

  m = MONTH_LABEL_RE.exec(text);
  if (m) {
    const month = MONTH_INDEX[m[1].toLowerCase()];
    const calYear = Number(m[2]);
    const fyStart = month >= 4 ? calYear : calYear - 1;
    const quarter = month >= 4 && month <= 6 ? 1 : month >= 7 && month <= 9 ? 2 : month >= 10 ? 3 : 4;
    return { year: fyStart, quarter, label: fyQuarterLabel(fyStart, quarter), kind: 'quarter' };
  }

  return null;
}

/** Human month range for a quarter label or Q number. */
export function getQuarterRange(q: string | number): string {
  if (typeof q === 'number') {
    return QUARTER_RANGE[q] || '';
  }
  const parsed = parseQuarter(q);
  if (parsed?.quarter) return QUARTER_RANGE[parsed.quarter] || '';
  const only = /^\s*Q([1-4])\s*$/i.exec(q || '');
  if (only) return QUARTER_RANGE[Number(only[1])] || '';
  return '';
}

/** UI display: `FY 2025–26 • Q1` (month names are never shown). */
export function formatPeriodDisplay(label: string | null | undefined): string {
  const raw = (label || '').trim();
  if (!raw || raw === '—') return raw;
  const parsed = parseQuarter(raw);
  if (!parsed) return raw;
  if (parsed.kind === 'year' || parsed.quarter === 0) {
    return fyShortDisplay(parsed.year);
  }
  return `${fyShortDisplay(parsed.year)} • Q${parsed.quarter}`;
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
  /** Full UI label including range. */
  displayLabel: string;
  year: number;
  quarter: number;
  range: string;
  reports: T[];
  distributorCount: number;
  totalQuantity: number;
  reportCountFull?: number;
};

export type YearBucket<T> = {
  year: number;
  fyLabel: string;
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
 * Group reports into FY → Quarter → Distributor rows.
 * Sort: FY desc, quarter desc (Q4→Q1), imported desc within quarter.
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
        displayLabel: formatPeriodDisplay(label),
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
      fyLabel: year ? fyShortDisplay(year) : 'Unknown',
      quarters: quarterEntries,
      reportCount: quarterEntries.reduce((s, q) => s + q.reports.length, 0),
    };
  });
}

export type PeriodSummary = {
  label: string;
  distributorCount: number;
  reportCount: number;
  totalQuantity: number;
};

/**
 * Overlay accurate full-filter period stats onto a page-local timeline.
 */
export function applyPeriodSummaries<T extends TimelineReport>(
  timeline: YearBucket<T>[],
  summaries: PeriodSummary[]
): YearBucket<T>[] {
  if (!summaries.length) return timeline;
  const byLabel = new Map<string, PeriodSummary>();
  for (const s of summaries) {
    const parsed = parseQuarter(s.label);
    const key = (parsed?.label || s.label).trim().toLowerCase();
    byLabel.set(key, s);
  }

  return timeline.map(year => {
    const quarters = year.quarters.map(q => {
      const hit = byLabel.get(q.label.trim().toLowerCase());
      if (!hit) return q;
      return {
        ...q,
        distributorCount: hit.distributorCount || q.distributorCount,
        totalQuantity: hit.totalQuantity,
        reportCountFull: hit.reportCount,
      };
    });
    const yearFromSummaries = summaries
      .filter(s => {
        const parsed = parseQuarter(s.label);
        return (parsed?.year ?? 0) === year;
      })
      .reduce((sum, s) => sum + (s.reportCount || 0), 0);
    return {
      ...year,
      quarters,
      reportCount:
        yearFromSummaries ||
        quarters.reduce((sum, q) => sum + (q.reportCountFull ?? q.reports.length), 0),
    };
  });
}

/** Flat overview from server period summaries (accurate; not page-local). */
export function overviewFromPeriodSummaries(
  summaries: PeriodSummary[]
): Array<
  Pick<
    QuarterBucket<TimelineReport>,
    'label' | 'displayLabel' | 'range' | 'distributorCount' | 'totalQuantity' | 'year' | 'quarter'
  >
> {
  const items = summaries.map(s => {
    const parsed = parseQuarter(s.label);
    const label = parsed?.label ?? s.label;
    return {
      label,
      displayLabel: formatPeriodDisplay(label),
      year: parsed?.year ?? 0,
      quarter: parsed?.quarter ?? 0,
      range: getQuarterRange(parsed?.quarter || s.label),
      distributorCount: s.distributorCount,
      totalQuantity: s.totalQuantity,
      reports: [] as TimelineReport[],
    };
  });
  items.sort((a, b) => {
    if (a.year !== b.year) return b.year - a.year;
    if (a.quarter !== b.quarter) return b.quarter - a.quarter;
    return b.label.localeCompare(a.label);
  });
  return items;
}

export function formatMt(qty: number): string {
  return qty.toLocaleString(undefined, {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  });
}

/** Rewrite known quarter tokens inside free text (audit details, etc.). */
export function formatPeriodsInText(text: string | null | undefined): string {
  if (!text) return '';
  let out = String(text);
  // FY 2025-26 • Q1  /  FY 2025–26 Q1
  out = out.replace(
    /\bFY\s*(\d{4})\s*[-–—/]\s*(\d{2}|\d{4})\s*[•·.\-]?\s*Q\s*([1-4])\b/gi,
    (full) => formatPeriodDisplay(full)
  );
  // Q2 FY 2025-26
  out = out.replace(
    /\bQ\s*([1-4])\s+FY\s*(\d{4})\s*[-–—/]\s*(\d{2}|\d{4})\b/gi,
    (full) => formatPeriodDisplay(full)
  );
  // Legacy Q1 2025
  out = out.replace(/\bQ([1-4])\s+(\d{4})\b/gi, (full) => formatPeriodDisplay(full));
  // Annual FY 2025-26
  out = out.replace(
    /\bFY\s*(\d{4})\s*[-–—/]\s*(\d{2}|\d{4})\b(?!\s*[•·.\-]?Q)/gi,
    (full) => formatPeriodDisplay(full)
  );
  return out;
}
