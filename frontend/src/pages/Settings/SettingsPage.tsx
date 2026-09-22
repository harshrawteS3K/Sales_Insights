import { useCallback, useEffect, useState, type CSSProperties, type FormEvent } from 'react';
import { Navigate } from 'react-router';
import { Cpu, RefreshCw, Save } from 'lucide-react';
import { useLayoutContext } from '../../hooks/useLayoutContext';
import { StatusBanner } from '../../components/common/StatusBanner';
import { apiRequest, ApiError } from '../../api';
import { isAdminRole } from '../../utils/rbac';
import { BLUE, BORDER, TEAL } from '../../constants/theme';

const inputStyle: CSSProperties = {
  width: '100%',
  padding: '9px 12px',
  fontSize: '0.875rem',
  border: `1px solid ${BORDER}`,
  borderRadius: 8,
  outline: 'none',
  background: 'white',
};

type LlmSettings = {
  provider: string;
  enabled: boolean;
  model: string;
  api_key_configured: boolean;
  api_key_masked: string;
  available_providers: string[];
  available_models: string[];
  timeout_seconds: number;
};

type UsagePayload = {
  totals: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
    estimated_cost_usd: number;
    calls: number;
  };
  recent: Array<{
    id: number;
    provider: string;
    model: string;
    purpose: string;
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
    estimated_cost_usd: number;
    email_id?: number | null;
    actor?: string | null;
    created_at?: string | null;
  }>;
};

export function SettingsPage() {
  const { userRole } = useLayoutContext();
  const [settings, setSettings] = useState<LlmSettings | null>(null);
  const [usage, setUsage] = useState<UsagePayload | null>(null);
  const [provider, setProvider] = useState('openai');
  const [model, setModel] = useState('gpt-4o-mini');
  const [enabled, setEnabled] = useState(true);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [sRes, uRes] = await Promise.all([
        apiRequest<{ success: boolean; data: LlmSettings }>('/settings/llm'),
        apiRequest<{ success: boolean; data: UsagePayload }>('/settings/llm/usage?limit=40'),
      ]);
      setSettings(sRes.data);
      setProvider(sRes.data.provider || 'openai');
      setModel(sRes.data.model || 'gpt-4o-mini');
      setEnabled(Boolean(sRes.data.enabled));
      setUsage(uRes.data);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load LLM settings');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isAdminRole(userRole)) void load();
  }, [userRole, load]);

  if (!isAdminRole(userRole)) {
    return <Navigate to="/" replace />;
  }

  const onSave = async (e: FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const res = await apiRequest<{ success: boolean; data: LlmSettings; message?: string }>(
        '/settings/llm',
        {
          method: 'PUT',
          body: { provider, model, enabled },
        },
      );
      setSettings(res.data);
      setSuccess(res.message || 'LLM settings saved');
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to save settings');
    } finally {
      setSaving(false);
    }
  };

  const totals = usage?.totals;

  return (
    <div style={{ padding: '24px 28px', maxWidth: 960 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
            <Cpu size={22} color={BLUE} />
            <h1 style={{ margin: 0, fontSize: '1.35rem', fontWeight: 700, color: '#0F172A' }}>
              Settings
            </h1>
          </div>
          <p style={{ margin: 0, fontSize: '0.875rem', color: '#64748B' }}>
            Admin-only LLM configuration, model selection, and token usage.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void load()}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6,
            padding: '8px 12px',
            borderRadius: 8,
            border: `1px solid ${BORDER}`,
            background: 'white',
            cursor: 'pointer',
            fontSize: '0.8125rem',
            fontWeight: 600,
            color: '#374151',
          }}
        >
          <RefreshCw size={14} /> Refresh
        </button>
      </div>

      {error && <StatusBanner message={error} type="error" style={{ marginBottom: 16 }} />}
      {success && <StatusBanner message={success} type="success" style={{ marginBottom: 16 }} />}

      <div
        style={{
          background: 'white',
          border: `1px solid ${BORDER}`,
          borderRadius: 12,
          padding: 20,
          marginBottom: 20,
        }}
      >
        <h2 style={{ margin: '0 0 14px', fontSize: '1rem', fontWeight: 700, color: '#0F172A' }}>
          LLM Provider
        </h2>
        {loading && !settings ? (
          <div style={{ color: '#64748B', fontSize: '0.875rem' }}>Loading…</div>
        ) : (
          <form onSubmit={onSave} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <span style={{ fontSize: '0.8125rem', fontWeight: 600, color: '#374151' }}>Provider</span>
              <select
                value={provider}
                onChange={e => setProvider(e.target.value)}
                style={inputStyle}
              >
                {(settings?.available_providers || ['openai']).map(p => (
                  <option key={p} value={p}>
                    {p === 'openai' ? 'OpenAI' : p}
                  </option>
                ))}
              </select>
            </label>

            <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <span style={{ fontSize: '0.8125rem', fontWeight: 600, color: '#374151' }}>Model</span>
              <select value={model} onChange={e => setModel(e.target.value)} style={inputStyle}>
                {(settings?.available_models || []).map(m => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
                {model && !(settings?.available_models || []).includes(model) && (
                  <option value={model}>{model}</option>
                )}
              </select>
            </label>

            <label
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                fontSize: '0.875rem',
                color: '#1E293B',
                fontWeight: 600,
              }}
            >
              <input
                type="checkbox"
                checked={enabled}
                onChange={e => setEnabled(e.target.checked)}
                style={{ width: 18, height: 18, accentColor: BLUE }}
              />
              Enable LLM fallback (when deterministic mapping is weak)
            </label>

            <div style={{ fontSize: '0.8125rem', color: '#64748B' }}>
              API key:{' '}
              {settings?.api_key_configured ? (
                <span style={{ color: '#059669', fontWeight: 600 }}>
                  configured ({settings.api_key_masked})
                </span>
              ) : (
                <span style={{ color: '#DC2626', fontWeight: 600 }}>
                  missing — set OPENAI_API_KEY in backend .env
                </span>
              )}
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <button
                type="submit"
                disabled={saving}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 6,
                  padding: '9px 16px',
                  borderRadius: 8,
                  border: 'none',
                  background: BLUE,
                  color: 'white',
                  fontWeight: 600,
                  cursor: saving ? 'not-allowed' : 'pointer',
                }}
              >
                <Save size={15} />
                {saving ? 'Saving…' : 'Save'}
              </button>
            </div>
          </form>
        )}
      </div>

      <div
        style={{
          background: 'white',
          border: `1px solid ${BORDER}`,
          borderRadius: 12,
          padding: 20,
        }}
      >
        <h2 style={{ margin: '0 0 14px', fontSize: '1rem', fontWeight: 700, color: '#0F172A' }}>
          Usage & cost
        </h2>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 12, marginBottom: 16 }}>
          {[
            { label: 'Calls', value: totals?.calls ?? 0 },
            { label: 'Prompt tokens', value: totals?.prompt_tokens ?? 0 },
            { label: 'Completion tokens', value: totals?.completion_tokens ?? 0 },
            {
              label: 'Est. cost (USD)',
              value: `$${(totals?.estimated_cost_usd ?? 0).toFixed(4)}`,
            },
          ].map(card => (
            <div
              key={card.label}
              style={{
                padding: '12px 14px',
                borderRadius: 10,
                background: 'rgba(31,95,168,0.05)',
                border: `1px solid rgba(31,95,168,0.12)`,
              }}
            >
              <div style={{ fontSize: '0.6875rem', fontWeight: 700, color: '#64748B', textTransform: 'uppercase' }}>
                {card.label}
              </div>
              <div style={{ fontSize: '1.125rem', fontWeight: 700, color: BLUE, marginTop: 4 }}>
                {card.value}
              </div>
            </div>
          ))}
        </div>

        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8125rem' }}>
            <thead>
              <tr style={{ borderBottom: `1px solid ${BORDER}`, textAlign: 'left' }}>
                {['When', 'Purpose', 'Model', 'Tokens', 'Cost', 'Email'].map(h => (
                  <th key={h} style={{ padding: '8px 10px', color: '#64748B', fontSize: '0.6875rem' }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(usage?.recent || []).length === 0 ? (
                <tr>
                  <td colSpan={6} style={{ padding: 16, color: '#94A3B8' }}>
                    No LLM calls recorded yet.
                  </td>
                </tr>
              ) : (
                usage!.recent.map(row => (
                  <tr key={row.id} style={{ borderBottom: `1px solid ${BORDER}` }}>
                    <td style={{ padding: '8px 10px', color: '#475569', whiteSpace: 'nowrap' }}>
                      {row.created_at ? new Date(row.created_at).toLocaleString() : '—'}
                    </td>
                    <td style={{ padding: '8px 10px' }}>{row.purpose}</td>
                    <td style={{ padding: '8px 10px' }}>{row.model}</td>
                    <td style={{ padding: '8px 10px' }}>{row.total_tokens}</td>
                    <td style={{ padding: '8px 10px', color: TEAL, fontWeight: 600 }}>
                      ${Number(row.estimated_cost_usd || 0).toFixed(5)}
                    </td>
                    <td style={{ padding: '8px 10px' }}>{row.email_id ?? '—'}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
