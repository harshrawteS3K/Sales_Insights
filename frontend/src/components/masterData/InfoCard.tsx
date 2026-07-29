import type { ReactNode } from 'react';
import { ArrowDown, Info } from 'lucide-react';
import { BORDER, BLUE, TEXT_SECONDARY } from '../../constants/theme';
import { FutureBadge } from './FutureBadge';

type FlowItem = {
  title: string;
  subtitle: string;
};

type Props = {
  title?: string;
  children?: ReactNode;
  flow?: FlowItem[];
  showFuture?: boolean;
};

const DEFAULT_FLOW: FlowItem[] = [
  { title: 'Customer Master', subtitle: 'Customer Dropdown' },
  { title: 'Product Master', subtitle: 'Product Dropdown' },
  { title: 'Future', subtitle: 'Segment-based Product Filtering' },
];

export function InfoCard({
  title = 'How Template Generation Works',
  children,
  flow = DEFAULT_FLOW,
  showFuture = true,
}: Props) {
  return (
    <div
      style={{
        background: 'white',
        border: `1px solid ${BORDER}`,
        borderRadius: 12,
        padding: '22px 24px',
        boxShadow: '0 1px 4px rgba(0,0,0,0.04)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
        <div
          style={{
            width: 32,
            height: 32,
            borderRadius: 8,
            background: 'rgba(31,95,168,0.08)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <Info size={16} color={BLUE} />
        </div>
        <h2 style={{ margin: 0, fontSize: '1rem', fontWeight: 700, color: '#111827' }}>{title}</h2>
        {showFuture && <FutureBadge />}
      </div>

      {children && (
        <p style={{ margin: '0 0 18px', fontSize: '0.8125rem', color: TEXT_SECONDARY, lineHeight: 1.55, maxWidth: 720 }}>
          {children}
        </p>
      )}

      {!children && (
        <p style={{ margin: '0 0 18px', fontSize: '0.8125rem', color: TEXT_SECONDARY, lineHeight: 1.55, maxWidth: 720 }}>
          Uploaded master datasets populate dropdown lists inside the official distributor Excel template.
          Segment-based product filtering will be added in a later phase.
        </p>
      )}

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
          gap: 16,
        }}
      >
        {flow.map((item, idx) => (
          <div
            key={item.title}
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'flex-start',
              gap: 8,
              padding: '14px 16px',
              background: idx === flow.length - 1 ? 'rgba(31,95,168,0.03)' : '#F9FAFB',
              border: `1px solid ${BORDER}`,
              borderRadius: 10,
              position: 'relative',
            }}
          >
            <div style={{ fontSize: '0.8125rem', fontWeight: 700, color: '#111827' }}>{item.title}</div>
            <ArrowDown size={14} color={BLUE} />
            <div style={{ fontSize: '0.8125rem', color: TEXT_SECONDARY, fontWeight: 500 }}>{item.subtitle}</div>
            {idx === flow.length - 1 && (
              <div style={{ marginTop: 4 }}>
                <FutureBadge />
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
