import { Download, FileOutput, Loader2, CheckCircle2, AlertCircle } from 'lucide-react';
import { BLUE, BORDER, GREEN, RED, TEXT_SECONDARY } from '../../constants/theme';
import { TemplatePreview } from './TemplatePreview';

export type TemplateGenStatus = 'idle' | 'generating' | 'ready' | 'error';

type Props = {
  status: TemplateGenStatus;
  message?: string | null;
  templateVersion?: string | null;
  generatedAt?: string | null;
  canGenerate: boolean;
  canDownload: boolean;
  onGenerate: () => void;
  onDownload: () => void;
};

function formatWhen(iso: string) {
  try {
    return new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
  } catch {
    return iso;
  }
}

export function TemplateGenerationCard({
  status,
  message,
  templateVersion,
  generatedAt,
  canGenerate,
  canDownload,
  onGenerate,
  onDownload,
}: Props) {
  const generating = status === 'generating';

  return (
    <div
      style={{
        background: 'white',
        border: `1px solid ${BORDER}`,
        borderRadius: 12,
        padding: '22px 22px 20px',
        boxShadow: '0 1px 4px rgba(0,0,0,0.04)',
        display: 'flex',
        flexDirection: 'column',
        gap: 16,
        minHeight: 420,
      }}
    >
      <div>
        <h2 style={{ margin: 0, fontSize: '1rem', fontWeight: 700, color: '#111827' }}>
          Generate Distributor Template
        </h2>
        <p style={{ margin: '6px 0 0', fontSize: '0.8125rem', color: TEXT_SECONDARY, lineHeight: 1.5 }}>
          Generate the official distributor template using uploaded master data.
        </p>
      </div>

      <TemplatePreview />

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>
        <button
          type="button"
          disabled={!canGenerate || generating}
          onClick={onGenerate}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 8,
            padding: '9px 16px',
            background: !canGenerate || generating ? '#9CA3AF' : BLUE,
            color: 'white',
            border: 'none',
            borderRadius: 8,
            fontSize: '0.8125rem',
            fontWeight: 600,
            cursor: !canGenerate || generating ? 'not-allowed' : 'pointer',
          }}
        >
          {generating ? <Loader2 size={15} style={{ animation: 'spin 1s linear infinite' }} /> : <FileOutput size={15} />}
          {generating ? 'Generating…' : 'Generate Template'}
        </button>

        <button
          type="button"
          disabled={!canDownload}
          onClick={onDownload}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 8,
            padding: '9px 16px',
            background: canDownload ? 'white' : '#F3F4F6',
            color: canDownload ? BLUE : '#9CA3AF',
            border: `1px solid ${canDownload ? BLUE : BORDER}`,
            borderRadius: 8,
            fontSize: '0.8125rem',
            fontWeight: 600,
            cursor: canDownload ? 'pointer' : 'not-allowed',
          }}
        >
          <Download size={15} />
          Download
        </button>
      </div>

      {!canGenerate && status === 'idle' && (
        <p style={{ margin: 0, fontSize: '0.75rem', color: TEXT_SECONDARY }}>
          Upload Customer Master and Product Master before generating the template.
        </p>
      )}

      {status === 'ready' && message && (
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
          <span style={{ fontSize: '0.8125rem', color: '#065F46', lineHeight: 1.45 }}>{message}</span>
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
            Generation Status
          </div>
          <div style={{ fontSize: '0.8125rem', fontWeight: 600, color: '#111827' }}>
            {status === 'ready'
              ? 'Template Ready'
              : status === 'generating'
                ? 'Generating'
                : status === 'error'
                  ? 'Failed'
                  : 'Not generated'}
          </div>
        </div>
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
            Template Version
          </div>
          <div style={{ fontSize: '0.8125rem', fontWeight: 600, color: '#111827' }}>
            {templateVersion || '—'}
          </div>
        </div>
        {generatedAt && (
          <div style={{ gridColumn: '1 / -1' }}>
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
              Generated At
            </div>
            <div style={{ fontSize: '0.8125rem', fontWeight: 600, color: '#111827' }}>
              {formatWhen(generatedAt)}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
