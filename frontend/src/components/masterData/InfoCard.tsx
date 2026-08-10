import type { ReactNode } from 'react';
import { ArrowDown, Info } from 'lucide-react';
import { BORDER, BLUE, TEXT_SECONDARY } from '../../constants/theme';

type FlowItem = {
  title: string;
  subtitle: string;
};

type Props = {
  title?: string;
  children?: ReactNode;
  flow?: FlowItem[];
};

const DEFAULT_FLOW: FlowItem[] = [
  {
    title: 'Product Master',
    subtitle:
      'Segment and Product dropdowns come from Product Master (Industry Type Description → Product Code). Customer Name is entered freely by the distributor.',
  },
  {
    title: 'Quarterly Template',
    subtitle:
      'One template per quarter: Name of Person, Reporting Quarter (manual, e.g. Q1 2026), then Sr. No., Customer Name, Segment, Product, Sales Quantity.',
  },
];

const DEFAULT_DESCRIPTION =
  'Upload Product Master, then generate the official quarterly distributor template. Segment selection filters Product. Customer names are typed manually — Customer Master is not required for template generation.';

export function InfoCard({
  title = 'How Template Generation Works',
  children,
  flow = DEFAULT_FLOW,
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
      </div>

      <p
        style={{
          margin: '0 0 18px',
          fontSize: '0.8125rem',
          color: TEXT_SECONDARY,
          lineHeight: 1.55,
          maxWidth: 820,
        }}
      >
        {children ?? DEFAULT_DESCRIPTION}
      </p>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
          gap: 16,
        }}
      >
        {flow.map(item => (
          <div
            key={item.title}
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'flex-start',
              gap: 8,
              padding: '14px 16px',
              background: '#F9FAFB',
              border: `1px solid ${BORDER}`,
              borderRadius: 10,
            }}
          >
            <div style={{ fontSize: '0.8125rem', fontWeight: 700, color: '#111827' }}>
              {item.title}
            </div>
            <ArrowDown size={14} color={BLUE} />
            <div
              style={{
                fontSize: '0.8125rem',
                color: TEXT_SECONDARY,
                fontWeight: 500,
                lineHeight: 1.5,
              }}
            >
              {item.subtitle}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
