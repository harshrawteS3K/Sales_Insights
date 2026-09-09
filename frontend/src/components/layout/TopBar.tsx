import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router';
import { Search, ChevronDown } from 'lucide-react';
import { BLUE, BORDER } from '../../constants/theme';

const quickLinks = [
  { name: 'Distributor Email Extraction', path: '/emails',            category: 'Emails'         },
  { name: 'Consolidated Sales Data',      path: '/consolidated-data', category: 'Data'           },
  { name: 'Distributor Management',       path: '/distributors',      category: 'Data'           },
  { name: 'ERP Header Dictionary',        path: '/admin/header-dictionary', category: 'Admin'   },
  { name: 'Sales Trend Analysis',         path: '/visualizations',   category: 'Visualizations' },
  { name: 'Distributor Performance',      path: '/visualizations',   category: 'Visualizations' },
  { name: 'Quarterly Sales Dashboard',    path: '/visualizations',   category: 'Visualizations' },
  { name: 'Product-wise Sales',           path: '/visualizations',   category: 'Visualizations' },
  { name: 'Region-wise Analytics',        path: '/visualizations',   category: 'Visualizations' },
];

export function TopBar({ userName = 'Debabrata C' }: { userName?: string }) {
  const navigate = useNavigate();
  const [search, setSearch] = useState('');
  const [showResults, setShowResults] = useState(false);
  const searchRef = useRef<HTMLDivElement>(null);

  const filteredReports = search.trim()
    ? quickLinks.filter(
        item =>
          item.name.toLowerCase().includes(search.toLowerCase()) ||
          item.category.toLowerCase().includes(search.toLowerCase())
      )
    : [];

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (searchRef.current && !searchRef.current.contains(event.target as Node)) {
        setShowResults(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  return (
    <div
      style={{
        height: 56,
        background: 'white',
        borderBottom: `1px solid ${BORDER}`,
        display: 'flex',
        alignItems: 'center',
        padding: '0 24px',
        gap: 16,
        flexShrink: 0,
      }}
    >
      {/* Search */}
      <div ref={searchRef} style={{ flex: 1, maxWidth: 400, position: 'relative' }}>
        <Search
          size={15}
          style={{
            position: 'absolute',
            left: 11,
            top: '50%',
            transform: 'translateY(-50%)',
            color: '#9CA3AF',
            pointerEvents: 'none',
            zIndex: 1,
          }}
        />
        <input
          type="text"
          value={search}
          onChange={e => { setSearch(e.target.value); setShowResults(true); }}
          onFocus={() => setShowResults(true)}
          placeholder="Search…"
          style={{
            width: '100%',
            height: 34,
            paddingLeft: 34,
            paddingRight: 12,
            border: `1px solid ${BORDER}`,
            borderRadius: 6,
            fontSize: '0.8125rem',
            color: '#374151',
            background: '#F9FAFB',
            outline: 'none',
            fontFamily: 'inherit',
            transition: 'border-color 0.15s, box-shadow 0.15s, background 0.15s',
          }}
        />

        {showResults && search.trim() && (
          <div
            style={{
              position: 'absolute',
              top: 'calc(100% + 4px)',
              left: 0,
              right: 0,
              background: 'white',
              border: `1px solid ${BORDER}`,
              borderRadius: 8,
              boxShadow: '0 4px 12px rgba(0,0,0,0.1)',
              maxHeight: 400,
              overflowY: 'auto',
              zIndex: 1000,
            }}
          >
            {filteredReports.length > 0 ? (
              <>
                <div style={{ padding: '8px 12px', borderBottom: `1px solid ${BORDER}`, fontSize: '0.75rem', fontWeight: 600, color: '#6B7280' }}>
                  {filteredReports.length} {filteredReports.length === 1 ? 'result' : 'results'} found
                </div>
                {filteredReports.map((item, idx) => (
                  <div
                    key={idx}
                    onClick={() => { setSearch(''); setShowResults(false); navigate(item.path); }}
                    style={{
                      padding: '10px 12px',
                      borderBottom: idx < filteredReports.length - 1 ? `1px solid ${BORDER}` : 'none',
                      cursor: 'pointer',
                      transition: 'background 0.12s',
                    }}
                    onMouseEnter={e => { e.currentTarget.style.background = '#F9FAFB'; }}
                    onMouseLeave={e => { e.currentTarget.style.background = 'white'; }}
                  >
                    <div style={{ fontSize: '0.8125rem', fontWeight: 600, color: BLUE, marginBottom: 4 }}>{item.name}</div>
                    <div style={{ fontSize: '0.75rem', color: '#6B7280' }}>{item.category}</div>
                  </div>
                ))}
              </>
            ) : (
              <div style={{ padding: '20px 12px', textAlign: 'center', color: '#6B7280', fontSize: '0.8125rem' }}>
                No reports found
              </div>
            )}
          </div>
        )}
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginLeft: 'auto' }}>
        {/* User */}
        <button
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            padding: '0 10px',
            height: 34,
            border: `1px solid ${BORDER}`,
            borderRadius: 6,
            background: 'white',
            cursor: 'pointer',
            transition: 'border-color 0.15s, box-shadow 0.15s',
          }}
          onMouseEnter={e => { e.currentTarget.style.borderColor = '#D1D5DB'; e.currentTarget.style.boxShadow = '0 1px 3px rgba(31,95,168,0.06)'; }}
          onMouseLeave={e => { e.currentTarget.style.borderColor = BORDER; e.currentTarget.style.boxShadow = 'none'; }}
        >
          <div style={{
            width: 22, height: 22, borderRadius: '50%', background: BLUE,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            boxShadow: 'inset 0 0 0 1px rgba(255,255,255,0.16)',
          }}>
            <span style={{ color: 'white', fontSize: '0.5625rem', fontWeight: 700 }}>
              {userName.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase()}
            </span>
          </div>
          <span style={{ fontSize: '0.8125rem', color: '#374151', fontWeight: 500 }}>{userName}</span>
          <ChevronDown size={13} color="#9CA3AF" />
        </button>
      </div>
    </div>
  );
}
