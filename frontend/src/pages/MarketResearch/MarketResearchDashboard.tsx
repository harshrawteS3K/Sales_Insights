import { useState, useEffect } from 'react';
import { useLocation } from 'react-router';
import { PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import { X, Download } from 'lucide-react';
import { BLUE, TEAL, TEXT, BORDER, BG, CHART_COLORS } from '../../constants/theme';
import type { RecentReport, MarketSizeEntry, CompetitorEntry } from '../../types';
import { MarketResearchService } from '../../services/marketResearch.service';
import { StatusBanner } from '../../components/common/StatusBanner';

const card = {
  background: 'white',
  border: `1px solid ${BORDER}`,
  borderRadius: 8,
  boxShadow: '0 1px 3px rgba(31,95,168,0.06)',
};

export function MarketResearchDashboard() {
  const location = useLocation();
  const [selectedReport, setSelectedReport] = useState<RecentReport | null>(null);

  const [loaded, setLoaded] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [kpis, setKpis] = useState<Array<{ title: string; value: string }>>([]);
  const [marketSizeData, setMarketSizeData] = useState<MarketSizeEntry[]>([]);
  const [competitorData, setCompetitorData] = useState<CompetitorEntry[]>([]);
  const [recentReports, setRecentReports] = useState<RecentReport[]>([]);

  const [competitorNames, setCompetitorNames] = useState<string[]>([]);
  const [mockCompetitors, setMockCompetitors] = useState<CompetitorEntry[]>([]);
  const [mockTopCustomers, setMockTopCustomers] = useState<Array<{ name: string; volume: number }>>([]);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [kpiData, mSize, comp, reports, cNames, mComp, mTopCust] = await Promise.all([
        MarketResearchService.getDashboardKPIs(),
        MarketResearchService.getMarketSizeData(),
        MarketResearchService.getCompetitorData(),
        MarketResearchService.getRecentReports(),
        MarketResearchService.getCompetitors(),
        MarketResearchService.getMockCompetitors(),
        MarketResearchService.getMockTopCustomers(),
      ]);
      setKpis(kpiData);
      setMarketSizeData(mSize);
      setCompetitorData(comp);
      setRecentReports(reports);
      setCompetitorNames(cNames.slice(0, 10));
      setMockCompetitors(mComp);
      setMockTopCustomers(mTopCust);
      setLoaded(true);
      if (kpiData.length === 0 && mSize.length === 0 && reports.length === 0) {
        setError('Market Research APIs are not available in Phase 1. This page will connect when backend endpoints are added.');
      }
    } catch (err) {
      setLoaded(false);
      setError(err instanceof Error ? err.message : 'Failed to load market research data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  useEffect(() => {
    if (location.state?.selectedReport) {
      setSelectedReport(location.state.selectedReport);
      window.history.replaceState({}, document.title);
    }
  }, [location]);

  const mockTableData: Array<Record<string, string | number>> = [];
  const totalRow = { customer: 'TOTAL', total: 0 } as Record<string, string | number>;

  return (
    <div>
      <div style={{ padding: '28px 32px 32px' }}>
        <div
          style={{
            background: 'linear-gradient(135deg, #1F5FA8 0%, #1FB7B5 100%)',
            padding: '28px 32px',
            borderRadius: 8,
            marginBottom: 24,
          }}
        >
          <h1 style={{ fontSize: '1.5rem', fontWeight: 700, color: 'white', marginBottom: 6 }}>Market Research Dashboard</h1>
          <p style={{ fontSize: '0.875rem', color: 'rgba(255,255,255,0.85)' }}>Outcome-driven insights for new market expansion</p>
        </div>

        <StatusBanner loading={loading} error={error} onRetry={loadData} loadingText="Loading market research…" />

        {loaded && (
          <>
            <div className="grid grid-cols-4 gap-5 mb-7">
              {kpis.map(kpi => (
                <KPICard key={kpi.title} title={kpi.title} value={kpi.value} />
              ))}
            </div>

            <div className="grid grid-cols-2 gap-5 mb-7">
              <div style={card}>
                <div style={{ padding: '18px 20px', borderBottom: `1px solid ${BORDER}` }}>
                  <h2 style={{ fontSize: '0.9375rem', fontWeight: 600, color: TEXT }}>Market Size by Country (MT)</h2>
                </div>
                <div style={{ padding: '24px 20px' }}>
                  <ResponsiveContainer width="100%" height={280} key="dashboard-market-size-chart">
                    <PieChart>
                      <Pie
                        data={marketSizeData}
                        cx="50%"
                        cy="50%"
                        labelLine={false}
                        label={entry => `${entry.name} (${entry.percent}%)`}
                        outerRadius={90}
                        fill="#8884d8"
                        dataKey="value"
                        nameKey="name"
                        id="market-size-pie"
                      >
                        {marketSizeData.map((entry, index) => (
                          <Cell key={`market-size-${entry.name}-${index}`} fill={CHART_COLORS[index % CHART_COLORS.length]} />
                        ))}
                      </Pie>
                      <Tooltip formatter={value => `${value} MT`} />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
              </div>

              <div style={card}>
                <div style={{ padding: '18px 20px', borderBottom: `1px solid ${BORDER}` }}>
                  <h2 style={{ fontSize: '0.9375rem', fontWeight: 600, color: TEXT }}>Market Share by Competitor</h2>
                </div>
                <div style={{ padding: '24px 20px' }}>
                  <ResponsiveContainer width="100%" height={280} key="dashboard-competitor-chart">
                    <BarChart data={competitorData}>
                      <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                      <YAxis tick={{ fontSize: 12 }} />
                      <Tooltip formatter={value => `${value}%`} />
                      <Bar dataKey="share" fill={TEAL} radius={[4, 4, 0, 0]} id="competitor-bar" />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </div>

            <div style={card}>
              <div style={{ padding: '14px 20px', borderBottom: `1px solid ${BORDER}` }}>
                <h2 style={{ fontSize: '0.9375rem', fontWeight: 600, color: TEXT }}>Recent Reports</h2>
              </div>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ background: BG }}>
                    {['Report Name', 'Country', 'Segment', 'Product', 'Market Size (MT)', 'Date'].map(h => (
                      <th
                        key={h}
                        style={{
                          padding: '9px 16px',
                          textAlign: 'left',
                          fontSize: '0.75rem',
                          fontWeight: 600,
                          color: BLUE,
                          letterSpacing: '0.03em',
                          borderBottom: `1px solid ${BORDER}`,
                        }}
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {recentReports.slice(0, 5).map((report, i) => (
                    <tr
                      key={i}
                      onClick={() => setSelectedReport(report)}
                      style={{
                        borderTop: i > 0 ? `1px solid ${BORDER}` : undefined,
                        cursor: 'pointer',
                        transition: 'background 0.12s',
                      }}
                      onMouseEnter={e => {
                        e.currentTarget.style.background = '#F9FAFB';
                      }}
                      onMouseLeave={e => {
                        e.currentTarget.style.background = 'white';
                      }}
                    >
                      <td style={{ padding: '10px 16px', fontSize: '0.8125rem', color: BLUE, fontWeight: 600 }}>{report.name}</td>
                      <td style={{ padding: '10px 16px', fontSize: '0.8125rem', color: TEXT }}>{report.country}</td>
                      <td style={{ padding: '10px 16px', fontSize: '0.8125rem', color: TEXT }}>{report.segment}</td>
                      <td style={{ padding: '10px 16px', fontSize: '0.8125rem', color: TEXT }}>{report.product}</td>
                      <td style={{ padding: '10px 16px', fontSize: '0.8125rem', color: TEXT }}>{report.marketSize}</td>
                      <td style={{ padding: '10px 16px', fontSize: '0.8125rem', color: '#6B7280' }}>{report.date}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {selectedReport && (
              <div
                style={{
                  position: 'fixed',
                  top: 0,
                  left: 0,
                  right: 0,
                  bottom: 0,
                  background: 'rgba(0,0,0,0.5)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  zIndex: 1000,
                  padding: 20,
                }}
                onClick={() => setSelectedReport(null)}
              >
                <div
                  style={{
                    background: 'white',
                    borderRadius: 12,
                    width: '100%',
                    maxWidth: 1400,
                    maxHeight: '90vh',
                    overflow: 'auto',
                    boxShadow: '0 20px 60px rgba(0,0,0,0.3)',
                  }}
                  onClick={e => e.stopPropagation()}
                >
                  <div
                    style={{
                      padding: '20px 24px',
                      borderBottom: `1px solid ${BORDER}`,
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      position: 'sticky',
                      top: 0,
                      background: 'white',
                      zIndex: 1,
                    }}
                  >
                    <div>
                      <h2 style={{ fontSize: '1.125rem', fontWeight: 600, color: TEXT, marginBottom: 4 }}>{selectedReport.name}</h2>
                      <p style={{ fontSize: '0.8125rem', color: '#6B7280' }}>
                        {selectedReport.country} • {selectedReport.segment} • {selectedReport.date}
                      </p>
                    </div>
                    <div style={{ display: 'flex', gap: 12 }}>
                      <button
                        onClick={() => setError('Report download is not available until Market Research APIs are added.')}
                        style={{
                          padding: '8px 16px',
                          fontSize: '0.8125rem',
                          fontWeight: 600,
                          color: BLUE,
                          background: 'white',
                          border: `1px solid ${BORDER}`,
                          borderRadius: 6,
                          cursor: 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          gap: 6,
                        }}
                      >
                        <Download size={15} strokeWidth={2} />
                        Download
                      </button>
                      <button
                        onClick={() => setSelectedReport(null)}
                        style={{
                          width: 32,
                          height: 32,
                          borderRadius: 6,
                          border: `1px solid ${BORDER}`,
                          background: 'white',
                          cursor: 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                        }}
                      >
                        <X size={18} />
                      </button>
                    </div>
                  </div>

                  <div style={{ padding: 24 }}>
                    <div style={{ ...card, marginBottom: 24 }}>
                      <div style={{ padding: '18px 20px', borderBottom: `1px solid ${BORDER}` }}>
                        <h3 style={{ fontSize: '0.9375rem', fontWeight: 600, color: TEXT }}>
                          Research Dashboard - {selectedReport.country} / {selectedReport.segment}
                        </h3>
                      </div>
                      <div style={{ overflowX: 'auto' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8125rem' }}>
                          <thead>
                            <tr>
                              <th
                                colSpan={2}
                                style={{
                                  padding: '10px 14px',
                                  textAlign: 'left',
                                  background: '#EAF4EC',
                                  border: `1px solid ${BORDER}`,
                                  fontSize: '0.8125rem',
                                  fontWeight: 600,
                                  color: TEXT,
                                }}
                              >
                                {selectedReport.country} / {selectedReport.segment}
                              </th>
                              <th
                                style={{
                                  padding: '10px 14px',
                                  textAlign: 'center',
                                  background: BG,
                                  border: `1px solid ${BORDER}`,
                                  fontSize: '0.75rem',
                                  fontWeight: 600,
                                  color: BLUE,
                                }}
                              >
                                MT
                              </th>
                            </tr>
                            <tr style={{ background: BG }}>
                              <th
                                style={{
                                  padding: '9px 14px',
                                  textAlign: 'left',
                                  border: `1px solid ${BORDER}`,
                                  fontSize: '0.75rem',
                                  fontWeight: 600,
                                  color: BLUE,
                                  minWidth: 140,
                                }}
                              >
                                Customer / Distributor
                              </th>
                              {competitorNames.map((name, i) => (
                                <th
                                  key={`modal-comp-header-${i}`}
                                  style={{
                                    padding: '9px 14px',
                                    textAlign: 'center',
                                    border: `1px solid ${BORDER}`,
                                    fontSize: '0.75rem',
                                    fontWeight: 600,
                                    color: BLUE,
                                    minWidth: 90,
                                  }}
                                >
                                  {name}
                                </th>
                              ))}
                              <th
                                style={{
                                  padding: '9px 14px',
                                  textAlign: 'center',
                                  border: `1px solid ${BORDER}`,
                                  fontSize: '0.75rem',
                                  fontWeight: 600,
                                  color: BLUE,
                                  background: '#FFF9E6',
                                  minWidth: 80,
                                }}
                              >
                                Total
                              </th>
                            </tr>
                          </thead>
                          <tbody>
                            {mockTableData.map((row, i) => (
                              <tr key={i}>
                                <td style={{ padding: '8px 14px', border: `1px solid ${BORDER}`, color: TEXT }}>{row.customer}</td>
                                <td style={{ padding: '8px 14px', border: `1px solid ${BORDER}`, textAlign: 'center', color: TEXT }}>{row.comp1}</td>
                                <td style={{ padding: '8px 14px', border: `1px solid ${BORDER}`, textAlign: 'center', color: TEXT }}>{row.comp2}</td>
                                <td style={{ padding: '8px 14px', border: `1px solid ${BORDER}`, textAlign: 'center', color: TEXT }}>{row.comp3}</td>
                                <td style={{ padding: '8px 14px', border: `1px solid ${BORDER}`, textAlign: 'center', color: TEXT }}>{row.comp4}</td>
                                <td style={{ padding: '8px 14px', border: `1px solid ${BORDER}`, textAlign: 'center', color: TEXT }}>{row.comp5}</td>
                                <td style={{ padding: '8px 14px', border: `1px solid ${BORDER}`, textAlign: 'center', color: TEXT }}>{row.comp6}</td>
                                <td style={{ padding: '8px 14px', border: `1px solid ${BORDER}`, textAlign: 'center', color: TEXT }}>{row.comp7}</td>
                                <td style={{ padding: '8px 14px', border: `1px solid ${BORDER}`, textAlign: 'center', color: TEXT }}>{row.comp8}</td>
                                <td style={{ padding: '8px 14px', border: `1px solid ${BORDER}`, textAlign: 'center', color: TEXT }}>{row.comp9}</td>
                                <td style={{ padding: '8px 14px', border: `1px solid ${BORDER}`, textAlign: 'center', color: TEXT }}>{row.comp10}</td>
                                <td
                                  style={{
                                    padding: '8px 14px',
                                    border: `1px solid ${BORDER}`,
                                    textAlign: 'center',
                                    fontWeight: 600,
                                    color: BLUE,
                                    background: '#FFFBF0',
                                  }}
                                >
                                  {row.total}
                                </td>
                              </tr>
                            ))}
                            <tr style={{ background: '#F0F9FF' }}>
                              <td style={{ padding: '8px 14px', border: `1px solid ${BORDER}`, fontWeight: 700, color: TEXT }}>{totalRow.customer}</td>
                              <td style={{ padding: '8px 14px', border: `1px solid ${BORDER}`, textAlign: 'center', fontWeight: 700, color: TEXT }}>{totalRow.comp1}</td>
                              <td style={{ padding: '8px 14px', border: `1px solid ${BORDER}`, textAlign: 'center', fontWeight: 700, color: TEXT }}>{totalRow.comp2}</td>
                              <td style={{ padding: '8px 14px', border: `1px solid ${BORDER}`, textAlign: 'center', fontWeight: 700, color: TEXT }}>{totalRow.comp3}</td>
                              <td style={{ padding: '8px 14px', border: `1px solid ${BORDER}`, textAlign: 'center', fontWeight: 700, color: TEXT }}>{totalRow.comp4}</td>
                              <td style={{ padding: '8px 14px', border: `1px solid ${BORDER}`, textAlign: 'center', fontWeight: 700, color: TEXT }}>{totalRow.comp5}</td>
                              <td style={{ padding: '8px 14px', border: `1px solid ${BORDER}`, textAlign: 'center', fontWeight: 700, color: TEXT }}>{totalRow.comp6}</td>
                              <td style={{ padding: '8px 14px', border: `1px solid ${BORDER}`, textAlign: 'center', fontWeight: 700, color: TEXT }}>{totalRow.comp7}</td>
                              <td style={{ padding: '8px 14px', border: `1px solid ${BORDER}`, textAlign: 'center', fontWeight: 700, color: TEXT }}>{totalRow.comp8}</td>
                              <td style={{ padding: '8px 14px', border: `1px solid ${BORDER}`, textAlign: 'center', fontWeight: 700, color: TEXT }}>{totalRow.comp9}</td>
                              <td style={{ padding: '8px 14px', border: `1px solid ${BORDER}`, textAlign: 'center', fontWeight: 700, color: TEXT }}>{totalRow.comp10}</td>
                              <td
                                style={{
                                  padding: '8px 14px',
                                  border: `1px solid ${BORDER}`,
                                  textAlign: 'center',
                                  fontWeight: 700,
                                  color: BLUE,
                                  background: '#FFF3CD',
                                }}
                              >
                                {totalRow.total}
                              </td>
                            </tr>
                          </tbody>
                        </table>
                      </div>
                    </div>

                    <div className="grid grid-cols-3 gap-5">
                      <div style={card}>
                        <div style={{ padding: '18px 20px', borderBottom: `1px solid ${BORDER}` }}>
                          <h3 style={{ fontSize: '0.9375rem', fontWeight: 600, color: TEXT }}>Market Share by Competitor</h3>
                        </div>
                        <div style={{ padding: '24px 20px' }}>
                          <ResponsiveContainer width="100%" height={220} key="modal-competitor-pie-chart">
                            <PieChart>
                              <Pie
                                data={mockCompetitors}
                                cx="50%"
                                cy="50%"
                                labelLine={false}
                                label={entry => `${entry.name} ${entry.share}%`}
                                outerRadius={70}
                                fill="#8884d8"
                                dataKey="share"
                                nameKey="name"
                                id="modal-competitor-pie"
                              >
                                {mockCompetitors.map((entry, index) => (
                                  <Cell key={`modal-pie-competitor-${entry.name}-${index}`} fill={CHART_COLORS[index % CHART_COLORS.length]} />
                                ))}
                              </Pie>
                              <Tooltip />
                            </PieChart>
                          </ResponsiveContainer>
                        </div>
                      </div>

                      <div style={card}>
                        <div style={{ padding: '18px 20px', borderBottom: `1px solid ${BORDER}` }}>
                          <h3 style={{ fontSize: '0.9375rem', fontWeight: 600, color: TEXT }}>Total Consumption</h3>
                        </div>
                        <div style={{ padding: '32px 20px', textAlign: 'center' }}>
                          <div style={{ fontSize: '2rem', fontWeight: 700, color: BLUE, marginBottom: 12 }}>{selectedReport.marketSize} MT</div>
                          <div style={{ fontSize: '1.25rem', fontWeight: 600, color: TEAL }}>
                            USD {(parseInt(selectedReport.marketSize.replace(/,/g, '')) * 2.2).toLocaleString()}
                          </div>
                        </div>
                      </div>

                      <div style={card}>
                        <div style={{ padding: '18px 20px', borderBottom: `1px solid ${BORDER}` }}>
                          <h3 style={{ fontSize: '0.9375rem', fontWeight: 600, color: TEXT }}>Top 3 Customers by Volume</h3>
                        </div>
                        <div style={{ padding: '24px 20px' }}>
                          <ResponsiveContainer width="100%" height={220} key="modal-customer-bar-chart">
                            <BarChart data={mockTopCustomers}>
                              <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                              <YAxis tick={{ fontSize: 11 }} />
                              <Tooltip formatter={value => `${value} MT`} />
                              <Bar dataKey="volume" fill={BLUE} radius={[4, 4, 0, 0]} id="modal-customer-bar" />
                            </BarChart>
                          </ResponsiveContainer>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function KPICard({ title, value }: { title: string; value: string }) {
  return (
    <div style={{ ...card, padding: '18px 20px' }}>
      <div style={{ fontSize: '0.8125rem', color: '#6B7280', fontWeight: 500, marginBottom: 10 }}>{title}</div>
      <div style={{ fontSize: '1.625rem', fontWeight: 700, color: BLUE }}>{value}</div>
    </div>
  );
}
