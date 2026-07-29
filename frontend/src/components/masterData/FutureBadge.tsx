import { BLUE } from '../../constants/theme';

export function FutureBadge({ label = 'Coming in Next Phase' }: { label?: string }) {
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        padding: '3px 10px',
        borderRadius: 4,
        fontSize: '0.6875rem',
        fontWeight: 600,
        letterSpacing: '0.03em',
        textTransform: 'uppercase',
        color: BLUE,
        background: 'rgba(31,95,168,0.08)',
        border: '1px solid rgba(31,95,168,0.18)',
        whiteSpace: 'nowrap',
      }}
    >
      {label}
    </span>
  );
}
