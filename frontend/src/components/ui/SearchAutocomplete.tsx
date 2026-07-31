import { useEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import { Search, X } from 'lucide-react';
import { BORDER } from '../../constants/theme';

type Props = {
  label: string;
  options: string[];
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  /** Value meaning "no filter" */
  allValue?: string;
  width?: number | string;
};

/**
 * Search-with-autocomplete filter (case-insensitive partial match).
 * Scales better than native <select> for hundreds/thousands of options.
 */
export function SearchAutocomplete({
  label,
  options,
  value,
  onChange,
  placeholder = 'Search…',
  allValue = 'All',
  width = 220,
}: Props) {
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  const displayValue = value && value !== allValue ? value : '';

  useEffect(() => {
    if (!open) {
      setQuery(displayValue);
    }
  }, [displayValue, open]);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) {
        setOpen(false);
        setQuery(displayValue);
      }
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [displayValue]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const base = options.filter(o => o && o !== allValue);
    if (!q) return base.slice(0, 40);
    return base.filter(o => o.toLowerCase().includes(q)).slice(0, 40);
  }, [options, query, allValue]);

  const select = (next: string) => {
    onChange(next);
    setQuery(next === allValue ? '' : next);
    setOpen(false);
  };

  return (
    <div ref={rootRef} style={{ position: 'relative', width, minWidth: 160 }}>
      <div style={{ fontSize: '0.65rem', color: '#6B7280', fontWeight: 600, marginBottom: 3 }}>
        {label}
      </div>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          height: 32,
          padding: '0 8px',
          border: `1px solid ${BORDER}`,
          borderRadius: 6,
          background: 'white',
        }}
      >
        <Search size={13} color="#9CA3AF" />
        <input
          value={query}
          placeholder={placeholder}
          onFocus={() => setOpen(true)}
          onChange={e => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onKeyDown={e => {
            if (e.key === 'Enter' && filtered[0]) {
              e.preventDefault();
              select(filtered[0]);
            }
            if (e.key === 'Escape') {
              setOpen(false);
              setQuery(displayValue);
            }
          }}
          style={{
            flex: 1,
            border: 'none',
            outline: 'none',
            fontSize: '0.8125rem',
            color: '#374151',
            background: 'transparent',
            minWidth: 0,
          }}
        />
        {(displayValue || query) && (
          <button
            type="button"
            title="Clear"
            onClick={() => select(allValue)}
            style={{
              border: 'none',
              background: 'transparent',
              padding: 0,
              cursor: 'pointer',
              display: 'flex',
              color: '#9CA3AF',
            }}
          >
            <X size={13} />
          </button>
        )}
      </div>
      {open && (
        <div
          style={{
            position: 'absolute',
            zIndex: 40,
            top: '100%',
            left: 0,
            right: 0,
            marginTop: 4,
            maxHeight: 240,
            overflowY: 'auto',
            background: 'white',
            border: `1px solid ${BORDER}`,
            borderRadius: 8,
            boxShadow: '0 8px 24px rgba(0,0,0,0.1)',
          }}
        >
          <button
            type="button"
            onClick={() => select(allValue)}
            style={optionStyle(value === allValue || !value)}
          >
            All {label}s
          </button>
          {filtered.length === 0 ? (
            <div style={{ padding: '10px 12px', fontSize: '0.75rem', color: '#9CA3AF' }}>
              No matches
            </div>
          ) : (
            filtered.map(opt => (
              <button
                key={opt}
                type="button"
                onClick={() => select(opt)}
                style={optionStyle(value === opt)}
              >
                {opt}
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}

function optionStyle(active: boolean): CSSProperties {
  return {
    display: 'block',
    width: '100%',
    textAlign: 'left',
    padding: '8px 12px',
    border: 'none',
    background: active ? '#EFF6FF' : 'transparent',
    color: active ? '#1D4ED8' : '#374151',
    fontSize: '0.8125rem',
    cursor: 'pointer',
  };
}
