import type { CSSProperties } from 'react';

export type ValidationSummaryShape = {
  total_rows?: number;
  imported_rows?: number;
  skipped_rows?: number;
  warning_count?: number;
  confidence_score?: number | null;
  warnings?: Array<{ reason: string; count: number }>;
  row_errors?: string[];
};

type Props = {
  confidenceScore?: number | null;
  incompleteRows?: number | null;
  importedRows?: number | null;
  expectedRows?: number | null;
  validationSummary?: ValidationSummaryShape | null;
  validationMessage?: string | null;
  /** compact = list cards; full = report details */
  variant?: 'full' | 'compact';
  style?: CSSProperties;
};

/**
 * Data Quality Warning — shown when confidence < 100% or rows were skipped.
 * Explains WHY confidence decreased using the persisted validation summary.
 */
export function DataQualityWarning({
  confidenceScore,
  incompleteRows,
  importedRows,
  expectedRows,
  validationSummary,
  validationMessage,
  variant = 'full',
  style,
}: Props) {
  const skipped =
    incompleteRows ??
    validationSummary?.skipped_rows ??
    0;
  const confidence =
    confidenceScore ??
    validationSummary?.confidence_score ??
    null;
  const warnings = validationSummary?.warnings ?? [];
  // Show when rows were skipped OR validation recorded skip reasons.
  // Confidence alone is not enough — the score can be <100% on fully valid files.
  const shouldShow = skipped > 0 || warnings.length > 0;

  if (!shouldShow) return null;

  const total =
    expectedRows ??
    validationSummary?.total_rows ??
    null;
  const imported =
    importedRows ??
    validationSummary?.imported_rows ??
    null;
  const isCompact = variant === 'compact';

  return (
    <div
      style={{
        marginTop: isCompact ? 8 : 14,
        padding: isCompact ? '8px 10px' : '12px 14px',
        background: 'rgba(180,83,9,0.08)',
        border: '1px solid rgba(180,83,9,0.28)',
        borderRadius: 8,
        color: '#92400E',
        fontSize: isCompact ? '0.75rem' : '0.8125rem',
        lineHeight: 1.5,
        maxWidth: isCompact ? 560 : undefined,
        ...style,
      }}
      role="status"
    >
      <div style={{ fontWeight: 700, marginBottom: 4 }}>
        ⚠ Data Quality Warning
      </div>
      <div style={{ marginBottom: isCompact ? 0 : 8 }}>
        {validationMessage ||
          (skipped > 0
            ? `Report imported successfully. ${skipped} row(s) were skipped because mandatory fields were missing or invalid.`
            : 'Report imported successfully. Confidence is below 100%.')}
      </div>

      {!isCompact && (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(110px, 1fr))',
            gap: 8,
            marginBottom: warnings.length ? 10 : 0,
          }}
        >
          {confidence != null && (
            <Metric label="Confidence Score" value={`${confidence}%`} />
          )}
          {total != null && <Metric label="Total Rows" value={String(total)} />}
          {imported != null && <Metric label="Imported" value={String(imported)} />}
          {skipped > 0 && <Metric label="Skipped" value={String(skipped)} />}
        </div>
      )}

      {isCompact && confidence != null && (
        <div style={{ marginTop: 4, opacity: 0.95 }}>
          Confidence {confidence}%
          {skipped > 0 ? ` · ${skipped} skipped` : ''}
          {imported != null ? ` · ${imported} imported` : ''}
        </div>
      )}

      {warnings.length > 0 && (
        <div style={{ marginTop: 8 }}>
          {!isCompact && (
            <div style={{ fontWeight: 600, marginBottom: 4 }}>Reasons</div>
          )}
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            {warnings.slice(0, isCompact ? 3 : 8).map(w => (
              <li key={w.reason}>
                {w.reason} ({w.count})
              </li>
            ))}
          </ul>
        </div>
      )}

      {!isCompact && skipped > 0 && (
        <div style={{ marginTop: 8, fontStyle: 'italic', opacity: 0.9 }}>
          Only valid records have been imported.
        </div>
      )}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div
      style={{
        background: 'rgba(255,255,255,0.55)',
        borderRadius: 6,
        padding: '6px 8px',
        border: '1px solid rgba(180,83,9,0.15)',
      }}
    >
      <div style={{ fontSize: '0.65rem', textTransform: 'uppercase', letterSpacing: 0.3, opacity: 0.85 }}>
        {label}
      </div>
      <div style={{ fontWeight: 700, fontSize: '0.9rem' }}>{value}</div>
    </div>
  );
}
