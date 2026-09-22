import type { CSSProperties } from 'react';
import { Loader2, X } from 'lucide-react';
import { BLUE, BORDER, RED } from '../../constants/theme';

type Props = {
  loading?: boolean;
  error?: string | null;
  message?: string | null;
  type?: 'error' | 'success' | 'info' | string;
  onClose?: () => void;
  onRetry?: () => void;
  loadingText?: string;
  style?: CSSProperties;
};

/** Minimal loading / status banner. */
export function StatusBanner({
  loading,
  error,
  message,
  type = 'error',
  onClose,
  onRetry,
  loadingText = 'Loading…',
  style,
}: Props) {
  const displayMsg = message || error;

  if (loading) {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          padding: '14px 18px',
          background: 'white',
          border: `1px solid ${BORDER}`,
          borderRadius: 8,
          color: BLUE,
          fontSize: '0.875rem',
          fontWeight: 600,
          ...style,
        }}
      >
        <Loader2 size={18} style={{ animation: 'spin 1s linear infinite' }} />
        {loadingText}
        <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
      </div>
    );
  }

  if (displayMsg) {
    const isSuccess = type === 'success';
    const bg = isSuccess ? 'rgba(5,150,105,0.08)' : 'rgba(217,58,47,0.06)';
    const borderColor = isSuccess ? 'rgba(5,150,105,0.25)' : 'rgba(217,58,47,0.25)';
    const textColor = isSuccess ? '#059669' : RED;

    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justify: 'space-between',
          padding: '12px 18px',
          background: bg,
          border: `1px solid ${borderColor}`,
          borderRadius: 8,
          marginBottom: 16,
          ...style,
        }}
      >
        <div style={{ fontSize: '0.875rem', color: textColor, fontWeight: 600 }}>
          {displayMsg}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          {onRetry && (
            <button
              type="button"
              onClick={onRetry}
              style={{
                padding: '6px 14px',
                background: BLUE,
                color: 'white',
                border: 'none',
                borderRadius: 6,
                fontSize: '0.8125rem',
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              Retry
            </button>
          )}
          {onClose && (
            <button
              type="button"
              onClick={onClose}
              style={{
                background: 'none',
                border: 'none',
                color: textColor,
                cursor: 'pointer',
                padding: 2,
                display: 'flex',
                alignItems: 'center',
              }}
            >
              <X size={16} />
            </button>
          )}
        </div>
      </div>
    );
  }

  return null;
}
