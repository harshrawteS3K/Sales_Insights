import { ChevronDown } from 'lucide-react';
import { BLUE, BORDER, TEAL, TEXT_SECONDARY } from '../../constants/theme';

function DropdownHint({ label }: { label: string }) {
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 4,
        padding: '3px 8px',
        borderRadius: 4,
        background: 'rgba(31,95,168,0.08)',
        border: '1px solid rgba(31,95,168,0.2)',
        color: BLUE,
        fontSize: '0.75rem',
        fontWeight: 600,
      }}
      title="Dropdown-enabled field"
    >
      {label}
      <ChevronDown size={12} strokeWidth={2.5} />
    </span>
  );
}

export function TemplatePreview() {
  const salesCols = [
    { key: 'sr', label: 'Sr. No.', dropdown: false },
    { key: 'customer', label: 'Customer Name', dropdown: false },
    { key: 'segment', label: 'Segment', dropdown: true },
    { key: 'product', label: 'Product', dropdown: true },
    { key: 'qty', label: 'Sales Quantity', dropdown: false },
  ];

  return (
    <div
      style={{
        border: `1px solid ${BORDER}`,
        borderRadius: 10,
        overflow: 'hidden',
        background: '#FAFBFC',
      }}
    >
      <div
        style={{
          padding: '10px 14px',
          background: 'linear-gradient(135deg, #1F5FA8 0%, #1898B0 55%, #1FB7B5 100%)',
          color: 'white',
          fontSize: '0.8125rem',
          fontWeight: 700,
          letterSpacing: '0.02em',
        }}
      >
        Quarterly Template Preview
      </div>

      <div style={{ padding: '14px 14px 16px' }}>
        <div
          style={{
            fontSize: '0.6875rem',
            fontWeight: 700,
            color: TEXT_SECONDARY,
            letterSpacing: '0.05em',
            textTransform: 'uppercase',
            marginBottom: 8,
          }}
        >
          Report Metadata
        </div>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))',
            gap: 8,
            marginBottom: 10,
          }}
        >
          {['Name of Person', 'Company Name', 'Reporting Quarter'].map(f => (
            <div
              key={f}
              style={{
                padding: '8px 10px',
                background: 'white',
                border: `1px solid ${BORDER}`,
                borderRadius: 6,
                fontSize: '0.75rem',
                color: '#374151',
                fontWeight: 500,
              }}
            >
              {f === 'Reporting Quarter' ? `${f} (type e.g. Q1 2026)` : f}
            </div>
          ))}
        </div>

        <div
          style={{
            marginBottom: 16,
            padding: '8px 10px',
            background: 'rgba(31,95,168,0.06)',
            border: `1px solid rgba(31,95,168,0.15)`,
            borderRadius: 6,
            fontSize: '0.6875rem',
            color: '#1E3A5F',
            lineHeight: 1.45,
          }}
        >
          <strong>Note:</strong> Q1 = April – June · Q2 = July – September · Q3 = October – December ·
          Q4 = January – March
        </div>

        <div
          style={{
            fontSize: '0.6875rem',
            fontWeight: 700,
            color: TEXT_SECONDARY,
            letterSpacing: '0.05em',
            textTransform: 'uppercase',
            marginBottom: 8,
          }}
        >
          Sales Table
        </div>

        <div style={{ overflowX: 'auto', border: `1px solid ${BORDER}`, borderRadius: 8, background: 'white' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 480 }}>
            <thead>
              <tr style={{ background: '#F3F4F6' }}>
                {salesCols.map(col => (
                  <th
                    key={col.key}
                    style={{
                      padding: '10px 12px',
                      textAlign: 'left',
                      fontSize: '0.75rem',
                      fontWeight: 600,
                      color: '#374151',
                      borderBottom: `1px solid ${BORDER}`,
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {col.dropdown ? <DropdownHint label={col.label} /> : col.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {[0, 1].map(row => (
                <tr key={row}>
                  {salesCols.map(col => (
                    <td
                      key={col.key}
                      style={{
                        padding: '10px 12px',
                        borderBottom: `1px solid ${BORDER}`,
                        fontSize: '0.75rem',
                        color: '#9CA3AF',
                      }}
                    >
                      {col.key === 'customer'
                        ? 'Type…'
                        : col.dropdown
                          ? 'Select…'
                          : '—'}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div style={{ marginTop: 10, fontSize: '0.75rem', color: TEXT_SECONDARY, display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <span style={{ width: 8, height: 8, borderRadius: 2, background: '#9CA3AF' }} />
            Customer Name — free text
          </span>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <span style={{ width: 8, height: 8, borderRadius: 2, background: BLUE }} />
            Segment — from Product Master
          </span>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <span style={{ width: 8, height: 8, borderRadius: 2, background: TEAL }} />
            Product — filtered by Segment (FG code)
          </span>
        </div>
      </div>
    </div>
  );
}
