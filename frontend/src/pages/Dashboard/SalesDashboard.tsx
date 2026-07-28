import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router';
import { Mail, Table2, BarChart3, ArrowUpRight } from 'lucide-react';
import { BLUE, TEAL, BORDER } from '../../constants/theme';
import { DashboardService, type DashboardSummary } from '../../services/dashboard.service';
import { StatusBanner } from '../../components/common/StatusBanner';
import { ApiError } from '../../api';

const quickModules = [
  {
    title: 'Distributor Emails',
    desc: 'Extract and process distributor emails using AI for automated sales data ingestion.',
    icon: Mail,
    path: '/emails',
    color: BLUE,
    bg: 'rgba(31,95,168,0.07)',
  },
  {
    title: 'Consolidated Data',
    desc: 'View and manage all extracted sales data in a structured spreadsheet-like interface.',
    icon: Table2,
    path: '/consolidated-data',
    color: '#7C3AED',
    bg: 'rgba(124,58,237,0.07)',
  },
  {
    title: 'Visualizations',
    desc: 'Analytical dashboards with charts, KPIs, and distributor performance insights.',
    icon: BarChart3,
    path: '/visualizations',
    color: TEAL,
    bg: 'rgba(31,183,181,0.07)',
  },
];

export function SalesDashboard() {
  const navigate = useNavigate();
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadSummary = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await DashboardService.getSummary();
      setSummary(data);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load dashboard summary');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSummary();
  }, []);

  return (
    <div style={{ fontFamily: "'Inter', system-ui, sans-serif", display: 'flex', flexDirection: 'column', height: '100%' }}>

      {/* Gradient Banner */}
      <div style={{
        background: 'linear-gradient(135deg, #1F5FA8 0%, #1898B0 45%, #1FB7B5 100%)',
        padding: '36px 40px 38px',
        flexShrink: 0,
      }}>

        <h1 style={{ fontSize: '1.625rem', fontWeight: 700, color: '#ffffff', margin: '0 0 8px', letterSpacing: '-0.01em' }}>
          Sales Insights
        </h1>
        <p style={{ fontSize: '0.9375rem', color: 'rgba(255,255,255,0.8)', margin: 0, fontWeight: 400 }}>
          AI-powered sales analytics for Apcotex Industries
          {summary?.last_sync_at ? ` · Last sync ${summary.last_sync_at}` : ''}
        </p>
      </div>

      {/* Module Cards */}
      <div style={{ flex: 1, padding: '32px 40px', background: '#F7FAFC' }}>
        <StatusBanner loading={loading && !summary} error={error} onRetry={loadSummary} loadingText="Loading dashboard…" />

        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(3, 1fr)',
          gap: 24,
          height: '100%',
          maxHeight: 340,
          marginTop: error || (loading && !summary) ? 16 : 0,
        }}>
          {quickModules.map(mod => {
            const Icon = mod.icon;
            return (
              <button
                key={mod.title}
                onClick={() => navigate(mod.path)}
                style={{
                  background: 'white',
                  border: `1px solid ${BORDER}`,
                  borderRadius: 14,
                  padding: '32px 28px',
                  textAlign: 'left',
                  cursor: 'pointer',
                  transition: 'box-shadow 0.15s, border-color 0.15s, transform 0.15s',
                  boxShadow: '0 1px 5px rgba(0,0,0,0.05)',
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'space-between',
                }}
                onMouseEnter={e => {
                  e.currentTarget.style.boxShadow = '0 8px 24px rgba(0,0,0,0.08)';
                  e.currentTarget.style.borderColor = mod.color;
                  e.currentTarget.style.transform = 'translateY(-2px)';
                }}
                onMouseLeave={e => {
                  e.currentTarget.style.boxShadow = '0 1px 5px rgba(0,0,0,0.05)';
                  e.currentTarget.style.borderColor = BORDER;
                  e.currentTarget.style.transform = 'translateY(0)';
                }}
              >
                <div>
                  <div style={{
                    width: 48, height: 48, borderRadius: 12, background: mod.bg,
                    display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 18,
                  }}>
                    <Icon size={24} color={mod.color} />
                  </div>
                  <div style={{ fontSize: '1.0625rem', fontWeight: 700, color: '#111827', marginBottom: 8 }}>
                    {mod.title}
                  </div>
                  <div style={{ fontSize: '0.875rem', color: '#6B7280', lineHeight: 1.5 }}>
                    {mod.desc}
                  </div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 20, color: mod.color, fontWeight: 600, fontSize: '0.8125rem' }}>
                  Open <ArrowUpRight size={15} />
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
