import React from 'react';
import { BORDER } from '../../constants/theme';

interface KpiCardProps {
  label: string;
  value: string;
  /** Optional override for value color */
  valueColor?: string;
}

/**
 * Generic KPI card used in Visualizations and MarketResearchDashboard.
 */
export function KpiCard({ label, value, valueColor = '#111827' }: KpiCardProps) {
  return (
    <div
      style={{
        background: 'white',
        border: `1px solid ${BORDER}`,
        borderRadius: 10,
        padding: '16px 20px',
        boxShadow: '0 1px 4px rgba(0,0,0,0.04)',
      }}
    >
      <div
        style={{
          fontSize: '0.6875rem',
          fontWeight: 700,
          color: '#9CA3AF',
          textTransform: 'uppercase',
          letterSpacing: '0.05em',
          marginBottom: 8,
        }}
      >
        {label}
      </div>
      <div style={{ fontSize: '1.25rem', fontWeight: 700, color: valueColor }}>
        {value}
      </div>
    </div>
  );
}
