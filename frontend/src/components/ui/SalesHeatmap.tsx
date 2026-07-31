import type { CSSProperties } from 'react';

type HeatmapData = {
  months: string[];
  distributors: string[];
  cells: Array<{ distributor: string; month: string; qty: number }>;
};

type Props = {
  data: HeatmapData;
  height?: number;
};

/** CSS-grid heatmap for distributor Ã— month quantity intensity. */
export function SalesHeatmap({ data, height = 320 }: Props) {
  const { months, distributors, cells } = data;
  if (!months.length || !distributors.length) {
    return (
      <div style={{ height, display: 'grid', placeItems: 'center', color: '#9CA3AF', fontSize: 13 }}>
        No data for heatmap
      </div>
    );
  }

  const lookup = new Map<string, number>();
  let max = 0;
  for (const c of cells) {
    lookup.set(`${c.distributor}||${c.month}`, c.qty);
    if (c.qty > max) max = c.qty;
  }

  const colorFor = (qty: number): string => {
    if (!qty || max <= 0) return '#F9FAFB';
    const t = Math.min(1, qty / max);
    // blue intensity scale
    const r = Math.round(239 - t * 180);
    const g = Math.round(246 - t * 140);
    const b = Math.round(255 - t * 40);
    return `rgb(${r},${g},${b})`;
  };

  return (
    <div style={{ overflowX: 'auto', maxHeight: height }}>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: `140px repeat(${months.length}, minmax(72px, 1fr))`,
          gap: 2,
          minWidth: 140 + months.length * 72,
        }}
      >
        <div />
        {months.map(m => (
          <div key={m} style={headerCell}>
            {m}
          </div>
        ))}
        {distributors.map(dist => (
          <div key={dist} style={{ display: 'contents' }}>
            <div style={rowLabel} title={dist}>
              {dist}
            </div>
            {months.map(m => {
              const qty = lookup.get(`${dist}||${m}`) || 0;
              return (
                <div
                  key={`${dist}-${m}`}
                  title={`${dist} Â· ${m}: ${qty.toLocaleString()} MT`}
                  style={{
                    ...cellBase,
                    background: colorFor(qty),
                    color: qty / (max || 1) > 0.55 ? '#fff' : '#374151',
                  }}
                >
                  {qty ? Math.round(qty).toLocaleString() : 'â€”'}
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

const headerCell: CSSProperties = {
  fontSize: 10,
  fontWeight: 600,
  color: '#6B7280',
  textAlign: 'center',
  padding: '4px 2px',
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
};

const rowLabel: CSSProperties = {
  fontSize: 11,
  color: '#374151',
  padding: '6px 8px',
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
  alignSelf: 'center',
};

const cellBase: CSSProperties = {
  fontSize: 10,
  textAlign: 'center',
  padding: '8px 4px',
  borderRadius: 4,
  fontWeight: 600,
};
