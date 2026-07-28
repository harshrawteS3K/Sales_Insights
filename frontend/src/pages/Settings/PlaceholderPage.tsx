import { useNavigate, useLocation } from 'react-router';
import { Construction } from 'lucide-react';
import { BLUE, TEAL, BORDER } from '../../constants/theme';

const PAGE_LABELS: Record<string, string> = {
  '/experiments': 'Experiments',
  '/products':    'Products',
  '/settings':    'Settings',
};

export function PlaceholderPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const label = PAGE_LABELS[location.pathname] || 'Page';

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: 'calc(100vh - 56px)',
        padding: 40,
        textAlign: 'center',
      }}
    >
      <div
        style={{
          width: 60,
          height: 60,
          borderRadius: 14,
          border: `2px solid ${BORDER}`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          marginBottom: 20,
        }}
      >
        <Construction size={28} color={BLUE} strokeWidth={1.5} />
      </div>
      <h2 style={{ color: BLUE, fontSize: '1.125rem', fontWeight: 700, marginBottom: 8 }}>
        {label}
      </h2>
      <p style={{ color: '#6B7280', fontSize: '0.875rem', maxWidth: 360, lineHeight: 1.6, marginBottom: 24 }}>
        This section is under development. It will be available in the next release.
      </p>
      <button
        onClick={() => navigate('/')}
        style={{
          background: TEAL,
          color: 'white',
          border: 'none',
          borderRadius: 7,
          padding: '9px 20px',
          fontSize: '0.875rem',
          fontWeight: 600,
          cursor: 'pointer',
        }}
      >
        Back to Dashboard
      </button>
    </div>
  );
}
