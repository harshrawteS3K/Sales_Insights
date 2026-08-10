import { useEffect, useState, type CSSProperties } from 'react';
import { Download, FileOutput, Loader2, CheckCircle2, AlertCircle } from 'lucide-react';
import { BLUE, BORDER, GREEN, RED, TEXT_SECONDARY } from '../../constants/theme';
import { TemplatePreview } from './TemplatePreview';
import { DistributorService } from '../../services/distributor.service';
import type { Distributor, TemplateGenerateMode } from '../../types';

export type TemplateGenStatus = 'idle' | 'generating' | 'ready' | 'error';

type Props = {
  status: TemplateGenStatus;
  message?: string | null;
  templateVersion?: string | null;
  generatedAt?: string | null;
  canGenerate: boolean;
  canDownload: boolean;
  mode: TemplateGenerateMode;
  distributorId: number | null;
  fallbackGeneric?: boolean;
  onModeChange: (mode: TemplateGenerateMode) => void;
  onDistributorChange: (id: number | null) => void;
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
  mode,
  distributorId,
  fallbackGeneric = false,
  onModeChange,
  onDistributorChange,
  onGenerate,
  onDownload,
}: Props) {
  const generating = status === 'generating';
  const [distributors, setDistributors] = useState<Distributor[]>([]);
  const [distLoading, setDistLoading] = useState(false);
  const [distError, setDistError] = useState<string | null>(null);

  useEffect(() => {
    if (mode !== 'distributor') return;
    let cancelled = false;
    setDistLoading(true);
    setDistError(null);
    DistributorService.list({ active_only: true, limit: 500 })
      .then(res => {
        if (cancelled) return;
        setDistributors(res.data);
      })
      .catch(err => {
        if (cancelled) return;
        setDistError(err instanceof Error ? err.message : 'Failed to load distributors');
        setDistributors([]);
      })
      .finally(() => {
        if (!cancelled) setDistLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [mode]);

  const distributorReady = mode === 'generic' || (distributorId != null && distributorId > 0);
  const generateEnabled = canGenerate && distributorReady && !generating;
  const generateLabel =
    mode === 'distributor' ? 'Generate Distributor Template' : 'Generate Generic Template';

  const radioStyle = (active: boolean): CSSProperties => ({
    display: 'flex',
    alignItems: 'flex-start',
    gap: 8,
    padding: '10px 12px',
    border: `1px solid ${active ? BLUE : BORDER}`,
    borderRadius: 8,
    background: active ? 'rgba(31,95,168,0.04)' : 'white',
    cursor: 'pointer',
  });

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
          Generate a generic free-text template, or a distributor-specific template whose Customer
          Name dropdown is built from that distributor’s full submission history. Reporting Quarter
          is entered later in the Excel file.
        </p>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        <label style={radioStyle(mode === 'generic')}>
          <input
            type="radio"
            name="template-mode"
            checked={mode === 'generic'}
            onChange={() => onModeChange('generic')}
            style={{ marginTop: 2 }}
          />
          <span>
            <span style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: '#111827' }}>
              Generic Template
            </span>
            <span style={{ fontSize: '0.75rem', color: TEXT_SECONDARY }}>
              Blank customer column — for first-time submissions with no prior history
            </span>
          </span>
        </label>
        <label style={radioStyle(mode === 'distributor')}>
          <input
            type="radio"
            name="template-mode"
            checked={mode === 'distributor'}
            onChange={() => onModeChange('distributor')}
            style={{ marginTop: 2 }}
          />
          <span>
            <span style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: '#111827' }}>
              Distributor-Specific Template
            </span>
            <span style={{ fontSize: '0.75rem', color: TEXT_SECONDARY }}>
              Customer dropdown = all historical customers for the selected distributor
            </span>
          </span>
        </label>
      </div>

      {mode === 'distributor' && (
        <div>
          <label
            style={{
              display: 'block',
              fontSize: '0.75rem',
              fontWeight: 600,
              color: '#374151',
              marginBottom: 6,
            }}
          >
            Distributor
          </label>
          <select
            value={distributorId ?? ''}
            onChange={e => {
              const v = e.target.value;
              onDistributorChange(v ? Number(v) : null);
            }}
            disabled={distLoading}
            style={{
              width: '100%',
              padding: '9px 12px',
              fontSize: '0.875rem',
              border: `1px solid ${BORDER}`,
              borderRadius: 8,
              outline: 'none',
              background: 'white',
              fontFamily: 'inherit',
            }}
          >
            <option value="">{distLoading ? 'Loading…' : 'Select distributor…'}</option>
            {distributors.map(d => (
              <option key={d.id} value={d.id}>
                {d.company}
                {d.name && d.name !== d.company ? ` (${d.name})` : ''}
              </option>
            ))}
          </select>
          {distError && (
            <p style={{ margin: '6px 0 0', fontSize: '0.75rem', color: RED }}>{distError}</p>
          )}
          {!distLoading && !distError && distributors.length === 0 && (
            <p style={{ margin: '6px 0 0', fontSize: '0.75rem', color: TEXT_SECONDARY }}>
              No active distributors found. Add one under Distributors first.
            </p>
          )}
        </div>
      )}

      <TemplatePreview />

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>
        <button
          type="button"
          disabled={!generateEnabled}
          onClick={onGenerate}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 8,
            padding: '9px 16px',
            background: !generateEnabled ? '#9CA3AF' : BLUE,
            color: 'white',
            border: 'none',
            borderRadius: 8,
            fontSize: '0.8125rem',
            fontWeight: 600,
            cursor: !generateEnabled ? 'not-allowed' : 'pointer',
          }}
        >
          {generating ? (
            <Loader2 size={15} style={{ animation: 'spin 1s linear infinite' }} />
          ) : (
            <FileOutput size={15} />
          )}
          {generating ? 'Generating…' : generateLabel}
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
          Upload Product Master before generating the template.
        </p>
      )}

      {canGenerate && mode === 'distributor' && !distributorReady && status === 'idle' && (
        <p style={{ margin: 0, fontSize: '0.75rem', color: TEXT_SECONDARY }}>
          Select a distributor to generate a distributor-specific template.
        </p>
      )}

      {status === 'ready' && message && (
        <div
          style={{
            display: 'flex',
            alignItems: 'flex-start',
            gap: 8,
            padding: '10px 12px',
            background: fallbackGeneric ? 'rgba(245,158,11,0.08)' : 'rgba(16,185,129,0.08)',
            border: `1px solid ${fallbackGeneric ? 'rgba(245,158,11,0.35)' : 'rgba(16,185,129,0.25)'}`,
            borderRadius: 8,
          }}
        >
          {fallbackGeneric ? (
            <AlertCircle size={16} color="#D97706" style={{ flexShrink: 0, marginTop: 1 }} />
          ) : (
            <CheckCircle2 size={16} color={GREEN} style={{ flexShrink: 0, marginTop: 1 }} />
          )}
          <span
            style={{
              fontSize: '0.8125rem',
              color: fallbackGeneric ? '#92400E' : '#065F46',
              lineHeight: 1.45,
            }}
          >
            {message}
          </span>
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
