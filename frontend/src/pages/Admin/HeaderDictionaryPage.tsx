import { useEffect, useState, type CSSProperties, type FormEvent, type KeyboardEvent } from 'react';
import { Navigate } from 'react-router';
import { Plus, Save, X, Loader2, BookMarked } from 'lucide-react';
import { useLayoutContext } from '../../hooks/useLayoutContext';
import { StatusBanner } from '../../components/common/StatusBanner';
import {
  HeaderDictionaryService,
  type HeaderDictionary,
} from '../../services/headerDictionary.service';
import { ApiError } from '../../api';
import { isAdminRole } from '../../utils/rbac';
import { BLUE, BORDER, RED, TEAL } from '../../constants/theme';

type SectionKey = keyof HeaderDictionary;

const SECTIONS: { key: SectionKey; title: string; hint: string }[] = [
  {
    key: 'customer',
    title: 'Customer Headers',
    hint: 'Party Name, Buyer, Account, Consignee, Client…',
  },
  {
    key: 'product',
    title: 'Product Headers',
    hint: 'Material, FG, Item Code, Grade, Description…',
  },
  {
    key: 'quantity',
    title: 'Quantity Headers',
    hint: 'Dispatch Qty, Sales Qty, Invoice Qty, Net Qty…',
  },
];

const inputStyle: CSSProperties = {
  flex: 1,
  minWidth: 160,
  padding: '8px 12px',
  fontSize: '0.875rem',
  border: `1px solid ${BORDER}`,
  borderRadius: 8,
  outline: 'none',
};

function Chip({
  label,
  onRemove,
}: {
  label: string;
  onRemove: () => void;
}) {
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        padding: '5px 10px',
        borderRadius: 999,
        background: 'rgba(31,95,168,0.08)',
        color: BLUE,
        fontSize: '0.8125rem',
        fontWeight: 600,
      }}
    >
      {label}
      <button
        type="button"
        onClick={onRemove}
        title={`Remove ${label}`}
        style={{
          display: 'inline-flex',
          border: 'none',
          background: 'transparent',
          color: '#6B7280',
          cursor: 'pointer',
          padding: 0,
          lineHeight: 1,
        }}
      >
        <X size={14} />
      </button>
    </span>
  );
}

export function HeaderDictionaryPage() {
  const { userRole } = useLayoutContext();
  const isAdmin = isAdminRole(userRole);

  const [data, setData] = useState<HeaderDictionary | null>(null);
  const [drafts, setDrafts] = useState<Record<SectionKey, string>>({
    customer: '',
    product: '',
    quantity: '',
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    if (!isAdmin) return;
    setLoading(true);
    HeaderDictionaryService.get()
      .then(setData)
      .catch((err: unknown) => {
        setError(err instanceof ApiError ? err.message : 'Failed to load header dictionary');
      })
      .finally(() => setLoading(false));
  }, [isAdmin]);

  if (!isAdmin) {
    return <Navigate to="/" replace />;
  }

  const addHeader = (key: SectionKey) => {
    if (!data) return;
    const raw = drafts[key].trim();
    if (!raw) return;
    const normalized = raw.toLowerCase().replace(/\s+/g, ' ');
    if (data[key].includes(normalized)) {
      setError(`Duplicate header in ${key}: ${normalized}`);
      return;
    }
    if (normalized.length > 100) {
      setError('Header max length is 100 characters');
      return;
    }
    setError(null);
    setData({ ...data, [key]: [...data[key], normalized] });
    setDrafts({ ...drafts, [key]: '' });
  };

  const removeHeader = (key: SectionKey, value: string) => {
    if (!data) return;
    setData({ ...data, [key]: data[key].filter(h => h !== value) });
  };

  const onKeyDown = (key: SectionKey, e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      addHeader(key);
    }
  };

  const handleSave = async (e?: FormEvent) => {
    e?.preventDefault();
    if (!data) return;
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const result = await HeaderDictionaryService.save(data);
      setData(result.dictionary);
      const addedCount = Object.values(result.changes.added).flat().length;
      const removedCount = Object.values(result.changes.removed).flat().length;
      setSuccess(
        `Saved. ${addedCount} added, ${removedCount} removed. Next ERP preview uses this dictionary immediately.`
      );
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : 'Failed to save header dictionary');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{ padding: '24px 28px', maxWidth: 960 }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 14, marginBottom: 20 }}>
        <div
          style={{
            width: 42,
            height: 42,
            borderRadius: 10,
            background: 'rgba(31,95,168,0.1)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
          }}
        >
          <BookMarked size={22} color={BLUE} />
        </div>
        <div>
          <h1 style={{ margin: 0, fontSize: '1.25rem', fontWeight: 700, color: BLUE }}>
            ERP Header Dictionary
          </h1>
          <p style={{ margin: '6px 0 0', color: '#6B7280', fontSize: '0.875rem', lineHeight: 1.5 }}>
            Configure synonyms for Customer, Product, and Quantity columns. Changes apply to the
            next ERP preview without restarting the server.
          </p>
        </div>
      </div>

      {error && (
        <div
          style={{
            marginBottom: 16,
            padding: '12px 16px',
            borderRadius: 10,
            border: '1px solid rgba(217,58,47,0.25)',
            background: 'rgba(217,58,47,0.06)',
            color: RED,
            fontSize: '0.875rem',
            fontWeight: 600,
          }}
        >
          {error}
        </div>
      )}
      {success && (
        <div
          style={{
            marginBottom: 16,
            padding: '12px 16px',
            borderRadius: 10,
            border: `1px solid ${BORDER}`,
            background: 'rgba(5,150,105,0.08)',
            color: '#047857',
            fontSize: '0.875rem',
            fontWeight: 600,
          }}
        >
          {success}
        </div>
      )}

      {loading || !data ? (
        <StatusBanner loading loadingText="Loading dictionary…" />
      ) : (
        <form onSubmit={handleSave}>
          {SECTIONS.map(section => (
            <section
              key={section.key}
              style={{
                marginBottom: 20,
                padding: 18,
                border: `1px solid ${BORDER}`,
                borderRadius: 12,
                background: 'white',
              }}
            >
              <div style={{ marginBottom: 12 }}>
                <h2 style={{ margin: 0, fontSize: '0.95rem', fontWeight: 700, color: '#111827' }}>
                  {section.title}
                </h2>
                <p style={{ margin: '4px 0 0', fontSize: '0.75rem', color: '#9CA3AF' }}>
                  {section.hint}
                </p>
              </div>

              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 14 }}>
                {data[section.key].length === 0 ? (
                  <span style={{ color: '#9CA3AF', fontSize: '0.8125rem' }}>No headers yet</span>
                ) : (
                  data[section.key].map(h => (
                    <Chip key={h} label={h} onRemove={() => removeHeader(section.key, h)} />
                  ))
                )}
              </div>

              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <input
                  style={inputStyle}
                  value={drafts[section.key]}
                  placeholder="Add header…"
                  onChange={e => setDrafts({ ...drafts, [section.key]: e.target.value })}
                  onKeyDown={e => onKeyDown(section.key, e)}
                />
                <button
                  type="button"
                  onClick={() => addHeader(section.key)}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 6,
                    padding: '8px 12px',
                    borderRadius: 8,
                    border: `1px solid ${BORDER}`,
                    background: 'white',
                    color: '#374151',
                    fontSize: '0.8125rem',
                    fontWeight: 600,
                    cursor: 'pointer',
                    whiteSpace: 'nowrap',
                  }}
                >
                  <Plus size={15} />
                  Add Header
                </button>
              </div>
            </section>
          ))}

          <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
            <button
              type="submit"
              disabled={saving}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 8,
                padding: '10px 18px',
                border: 'none',
                borderRadius: 8,
                background: saving ? '#93C5FD' : TEAL,
                color: 'white',
                fontSize: '0.875rem',
                fontWeight: 700,
                cursor: saving ? 'wait' : 'pointer',
              }}
            >
              {saving ? <Loader2 size={16} /> : <Save size={16} />}
              {saving ? 'Saving…' : 'Save Changes'}
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
