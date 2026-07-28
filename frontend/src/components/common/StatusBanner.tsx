import { Loader2 } from 'lucide-react';
import { BLUE, BORDER, RED } from '../../constants/theme';

type Props = {
  loading?: boolean;
  error?: string | null;
  onRetry?: () => void;
  loadingText?: string;
};

/** Minimal loading / error banner — no layout redesign. */
export function StatusBanner({
  loading,
  error,
  onRetry,
  loadingText = 'Loading…',
}: Props) {
  if (loading) {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          padding: '16px 20px',
          background: 'white',
          border: `1px solid ${BORDER}`,
          borderRadius: 10,
          color: BLUE,
          fontSize: '0.875rem',
          fontWeight: 600,
        }}
      >
        <Loader2 size={18} style={{ animation: 'spin 1s linear infinite' }} />
        {loadingText}
        <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
      </div>
    );
  }

  if (error) {
    return (
      <div
        style={{
          padding: '16px 20px',
          background: 'rgba(217,58,47,0.06)',
          border: '1px solid rgba(217,58,47,0.25)',
          borderRadius: 10,
          marginBottom: 16,
        }}
      >
        <div style={{ fontSize: '0.875rem', color: RED, fontWeight: 600, marginBottom: onRetry ? 10 : 0 }}>
          {error}
        </div>
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            style={{
              padding: '8px 16px',
              background: BLUE,
              color: 'white',
              border: 'none',
              borderRadius: 8,
              fontSize: '0.8125rem',
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            Retry
          </button>
        )}
      </div>
    );
  }

  return null;
}
