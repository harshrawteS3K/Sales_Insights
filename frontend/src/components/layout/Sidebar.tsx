import { useNavigate, useLocation } from 'react-router';
import {
  LayoutDashboard,
  Mail,
  Table2,
  BarChart3,
  Settings,
  LogOut,
} from 'lucide-react';
import APCOTEX_LOGO from '../../assets/images/apcotexindustrieslogo.png';
import { BLUE, TEAL, RED, BORDER } from '../../constants/theme';

const mainNavItems = [
  { path: '/',                  label: 'Dashboard',         icon: LayoutDashboard, exact: true },
  { path: '/emails',            label: 'Emails',            icon: Mail             },
  { path: '/consolidated-data', label: 'Consolidated Data', icon: Table2           },
  { path: '/visualizations',   label: 'Visualizations',    icon: BarChart3        },
];

export function Sidebar({
  userName = 'Debabrata C',
  userTitle = 'CMO',
  userRole,
  onLogout,
}: {
  userName?: string;
  userTitle?: string;
  userRole?: 'admin' | 'user' | null;
  onLogout?: () => void;
}) {
  const navigate = useNavigate();
  const location = useLocation();

  const filteredNavItems = mainNavItems.filter(item => {
    if ('adminOnly' in item && item.adminOnly && userRole !== 'admin') return false;
    return true;
  });

  const isActive = (item: { path: string; exact?: boolean }) => {
    if (item.exact) return location.pathname === item.path;
    return location.pathname === item.path || location.pathname.startsWith(item.path + '/');
  };

  return (
    <div
      style={{
        width: 240,
        minWidth: 240,
        background: 'white',
        borderRight: `1px solid ${BORDER}`,
        display: 'flex',
        flexDirection: 'column',
        height: '100vh',
        flexShrink: 0,
      }}
    >
      <div style={{ padding: '10px 20px', borderBottom: `1px solid ${BORDER}`, flexShrink: 0 }}>
        <img src={APCOTEX_LOGO} alt="Apcotex" style={{ height: 60, width: 'auto' }} />
      </div>

      <div style={{ padding: '16px 20px 6px', flexShrink: 0 }}>
        <span style={{
          fontSize: '0.6875rem',
          color: '#9CA3AF',
          letterSpacing: '0.07em',
          textTransform: 'uppercase',
          fontWeight: 600,
          display: 'inline-flex',
          alignItems: 'center',
          gap: 6,
        }}>
          Workspace
          <span style={{ width: 6, height: 6, borderRadius: '50%', background: RED }} />
        </span>
      </div>

      <nav style={{ flex: 1, overflowY: 'auto' }}>
        {filteredNavItems.map(item => {
          const active = isActive(item);
          const Icon = item.icon;
          return (
            <button
              key={item.path}
              onClick={() => navigate(item.path)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                width: '100%',
                padding: '8px 20px',
                background: active ? 'rgba(31,95,168,0.06)' : 'transparent',
                border: 'none',
                borderLeft: active ? `2px solid ${TEAL}` : '2px solid transparent',
                color: active ? BLUE : '#6B7280',
                cursor: 'pointer',
                textAlign: 'left',
                fontSize: '0.875rem',
                fontWeight: active ? 600 : 400,
                transition: 'background 0.12s, color 0.12s',
              }}
              onMouseEnter={e => {
                if (!active) {
                  e.currentTarget.style.background = '#F9FAFB';
                  e.currentTarget.style.color = '#374151';
                }
              }}
              onMouseLeave={e => {
                if (!active) {
                  e.currentTarget.style.background = 'transparent';
                  e.currentTarget.style.color = '#6B7280';
                }
              }}
            >
              <Icon size={17} strokeWidth={active ? 2 : 1.5} style={{ flexShrink: 0 }} />
              <span>{item.label}</span>
            </button>
          );
        })}
      </nav>

      <div style={{ borderTop: `1px solid ${BORDER}`, flexShrink: 0 }}>
        <button
          onClick={() => navigate('/settings')}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            width: '100%',
            padding: '8px 20px',
            background: 'transparent',
            border: 'none',
            borderLeft: '2px solid transparent',
            color: '#6B7280',
            cursor: 'pointer',
            fontSize: '0.875rem',
          }}
        >
          <Settings size={17} strokeWidth={1.5} />
          Settings
        </button>

        <div style={{ borderTop: `1px solid ${BORDER}` }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '12px 20px' }}>
            <div
              style={{
                width: 30,
                height: 30,
                borderRadius: '50%',
                background: BLUE,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexShrink: 0,
              }}
            >
              <span style={{ color: 'white', fontSize: '0.6875rem', fontWeight: 700 }}>
                {userName.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase()}
              </span>
            </div>

            <div style={{ minWidth: 0, flex: 1 }}>
              <div style={{ color: '#1F2937', fontSize: '0.8125rem', fontWeight: 600, lineHeight: 1.3 }}>
                {userName}
              </div>
              <div style={{
                color: '#9CA3AF',
                fontSize: '0.6875rem',
                lineHeight: 1.3,
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
              }}>
                {userTitle}
              </div>
            </div>

            <button
              onClick={onLogout}
              title="Logout"
              style={{
                background: 'transparent',
                border: 'none',
                color: '#6B7280',
                cursor: 'pointer',
                padding: 4,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                borderRadius: 4,
                transition: 'background 0.12s, color 0.12s',
              }}
              onMouseEnter={e => {
                e.currentTarget.style.background = 'rgba(217,58,47,0.08)';
                e.currentTarget.style.color = RED;
              }}
              onMouseLeave={e => {
                e.currentTarget.style.background = 'transparent';
                e.currentTarget.style.color = '#6B7280';
              }}
            >
              <LogOut size={16} strokeWidth={2} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
