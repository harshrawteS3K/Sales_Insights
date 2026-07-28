import React from 'react';
import { BORDER } from '../../constants/theme';

interface ChartCardProps {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  style?: React.CSSProperties;
}

/**
 * Generic chart container card extracted from Visualizations.tsx.
 */
export function ChartCard({ title, subtitle, children, style }: ChartCardProps) {
  return (
    <div
      style={{
        background: 'white',
        border: `1px solid ${BORDER}`,
        borderRadius: 12,
        padding: '20px 24px',
        boxShadow: '0 1px 4px rgba(0,0,0,0.04)',
        ...style,
      }}
    >
      <div style={{ marginBottom: 16 }}>
        <div style={{ fontSize: '0.9375rem', fontWeight: 700, color: '#111827', marginBottom: 2 }}>
          {title}
        </div>
        {subtitle && (
          <div style={{ fontSize: '0.75rem', color: '#9CA3AF' }}>{subtitle}</div>
        )}
      </div>
      {children}
    </div>
  );
}
