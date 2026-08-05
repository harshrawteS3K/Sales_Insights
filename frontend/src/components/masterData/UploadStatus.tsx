import { CheckCircle2, AlertCircle, Loader2 } from 'lucide-react';
import { GREEN, RED, BLUE, BORDER, TEXT_SECONDARY } from '../../constants/theme';

export type UploadStatusState = 'idle' | 'uploading' | 'success' | 'error';

type Props = {
  status: UploadStatusState;
  progress?: number | null;
  message?: string | null;
  lastUploaded?: string | null;
  recordsImported?: number | null;
  fileName?: string | null;
};

function formatWhen(iso: string) {
  try {
    return new Date(iso).toLocaleString(undefined, {
      dateStyle: 'medium',
      timeStyle: 'short',
    });
  } catch {
    return iso;
  }
}

export function UploadStatus({
  status,
  progress,
  message,
  lastUploaded,
  recordsImported,
  fileName,
}: Props) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {status === 'uploading' && (
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
            <Loader2 size={14} color={BLUE} style={{ animation: 'spin 1s linear infinite' }} />
            <span style={{ fontSize: '0.8125rem', color: BLUE, fontWeight: 600 }}>
              Uploading{progress != null ? ` · ${progress}%` : '…'}
            </span>
          </div>
          <div style={{ height: 6, background: '#E5E7EB', borderRadius: 3, overflow: 'hidden' }}>
            <div
              style={{
                height: '100%',
                width: `${progress ?? 0}%`,
                background: `linear-gradient(90deg, ${BLUE}, #1FB7B5)`,
                borderRadius: 3,
                transition: 'width 0.2s ease',
              }}
            />
          </div>
        </div>
      )}

      {status === 'success' && message && (
        <div
          style={{
            display: 'flex',
            alignItems: 'flex-start',
            gap: 8,
            padding: '10px 12px',
            background: 'rgba(16,185,129,0.08)',
            border: '1px solid rgba(16,185,129,0.25)',
            borderRadius: 8,
          }}
        >
          <CheckCircle2 size={16} color={GREEN} style={{ flexShrink: 0, marginTop: 1 }} />
          <span style={{ fontSize: '0.8125rem', color: '#065F46', lineHeight: 1.45, whiteSpace: 'pre-line' }}>{message}</span>
        </div>
      )}

      {status === 'error' && message && (
        <div
          style={{
            display: 'flex',
            alignItems: 'flex-start',
            gap: 8,
            padding: '10px 12px',
            background: 'rgba(217,58,47,0.07)',
            border: '1px solid rgba(217,58,47,0.25)',
            borderRadius: 8,
          }}
        >
          <AlertCircle size={16} color={RED} style={{ flexShrink: 0, marginTop: 1 }} />
          <span style={{ fontSize: '0.8125rem', color: '#991B1B', lineHeight: 1.45 }}>{message}</span>
        </div>
      )}

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          gap: 10,
          padding: '12px 14px',
          background: '#F9FAFB',
          border: `1px solid ${BORDER}`,
          borderRadius: 8,
        }}
      >
        <Meta label="Status" value={statusLabel(status)} />
        <Meta
          label="Last Uploaded"
          value={lastUploaded ? formatWhen(lastUploaded) : '—'}
        />
        <Meta label="Selected File" value={fileName || '—'} />
        <Meta
          label="Records Imported"
          value={recordsImported != null ? recordsImported.toLocaleString() : '—'}
        />
      </div>
    </div>
  );
}

function statusLabel(status: UploadStatusState) {
  switch (status) {
    case 'uploading':
      return 'In progress';
    case 'success':
      return 'Completed';
    case 'error':
      return 'Failed';
    default:
      return 'Ready';
  }
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div
        style={{
          fontSize: '0.6875rem',
          fontWeight: 600,
          color: TEXT_SECONDARY,
          letterSpacing: '0.04em',
          textTransform: 'uppercase',
          marginBottom: 4,
        }}
      >
        {label}
      </div>
      <div
        style={{
          fontSize: '0.8125rem',
          fontWeight: 600,
          color: '#111827',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}
        title={value}
      >
        {value}
      </div>
    </div>
  );
}
