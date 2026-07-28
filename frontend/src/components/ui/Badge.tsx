import React from 'react';

interface ConfidenceBadgeProps {
  score: number;
}

/**
 * Confidence score badge — green ≥95, amber ≥80, red <80.
 * Extracted from EmailsModule.tsx.
 */
export function ConfidenceBadge({ score }: ConfidenceBadgeProps) {
  const color = score >= 95 ? '#059669' : score >= 80 ? '#D97706' : '#D93A2F';
  const bg    = score >= 95 ? 'rgba(5,150,105,0.09)' : score >= 80 ? 'rgba(217,119,6,0.09)' : 'rgba(217,58,47,0.09)';

  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        padding: '5px 14px',
        borderRadius: 20,
        fontSize: '0.875rem',
        fontWeight: 700,
        color,
        background: bg,
      }}
    >
      {score}%
    </span>
  );
}

interface AuditActionBadgeProps {
  action: string;
}

const ACTION_COLORS: Record<string, string> = {
  Created: '#10B981',
  Updated: '#3B82F6',
  Deleted: '#EF4444',
  Viewed:  '#6B7280',
};

/**
 * Audit action badge — maps action type to a colour.
 * Extracted from AuditTrail.tsx.
 */
export function AuditActionBadge({ action }: AuditActionBadgeProps) {
  const color = ACTION_COLORS[action] ?? '#6B7280';
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        padding: '4px 8px',
        borderRadius: 4,
        fontSize: '0.75rem',
        fontWeight: 500,
        color,
        background: `${color}15`,
      }}
    >
      {action}
    </span>
  );
}
