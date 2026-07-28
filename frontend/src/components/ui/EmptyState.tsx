import React from 'react';
import { BORDER, BLUE } from '../../constants/theme';

interface EmptyStateProps {
  icon: React.ReactNode;
  title: string;
  description?: string;
  action?: React.ReactNode;
}

/**
 * Reusable empty state component — used when a page has no data loaded.
 */
export function EmptyState({ icon, title, description, action }: EmptyStateProps) {
  return (
    <div
      style={{
        background: 'white',
        border: `1px solid ${BORDER}`,
        borderRadius: 12,
        padding: '72px 32px',
        textAlign: 'center',
        boxShadow: '0 1px 4px rgba(0,0,0,0.04)',
      }}
    >
      <div
        style={{
          width: 64,
          height: 64,
          borderRadius: 16,
          background: 'rgba(31,95,168,0.07)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          margin: '0 auto 16px',
        }}
      >
        {icon}
      </div>
      <div style={{ fontSize: '1rem', fontWeight: 700, color: '#374151', marginBottom: 8 }}>
        {title}
      </div>
      {description && (
        <div style={{ fontSize: '0.875rem', color: '#9CA3AF', marginBottom: action ? 24 : 0 }}>
          {description}
        </div>
      )}
      {action}
    </div>
  );
}
