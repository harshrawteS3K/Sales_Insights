import { useState, useEffect } from 'react';
import { Search, Download, Eye, Filter } from 'lucide-react';
import { useLayoutContext } from '../../hooks/useLayoutContext';
import { AuditActionBadge } from '../../components/ui/Badge';
import type { AuditLog, AuditAction } from '../../types';
import { AuditTrailService } from '../../services/auditTrail.service';
import { ApiError } from '../../api';
import { StatusBanner } from '../../components/common/StatusBanner';

export function AuditTrail() {
  const { userRole } = useLayoutContext();
  const [searchTerm, setSearchTerm] = useState('');
  const [filterAction, setFilterAction] = useState<AuditAction | 'All'>('All');
  const [selectedLog, setSelectedLog] = useState<AuditLog | null>(null);

  const [loaded, setLoaded] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [auditLogs, setAuditLogs] = useState<AuditLog[]>([]);

  const loadAuditLogs = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await AuditTrailService.getAuditLogs();
      setAuditLogs(data);
      setLoaded(true);
    } catch (err) {
      setLoaded(false);
      setError(err instanceof ApiError ? err.message : 'Failed to load audit logs');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAuditLogs();
  }, []);

  const filteredLogs = auditLogs.filter(log => {
    const matchesSearch =
      searchTerm === '' ||
      log.user.toLowerCase().includes(searchTerm.toLowerCase()) ||
      log.action.toLowerCase().includes(searchTerm.toLowerCase()) ||
      log.details.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (log.reportName && log.reportName.toLowerCase().includes(searchTerm.toLowerCase()));

    const matchesFilter = filterAction === 'All' || log.action === filterAction;

    return matchesSearch && matchesFilter;
  });

  const handleExport = () => {
    const csvContent = [
      ['ID', 'User', 'Action', 'Details', 'Timestamp', 'Report Name'],
      ...filteredLogs.map(log => [log.id, log.user, log.action, log.details, log.timestamp, log.reportName || '']),
    ]
      .map(row => row.join(','))
      .join('\n');

    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `audit-trail-${new Date().toISOString().split('T')[0]}.csv`;
    a.click();
    window.URL.revokeObjectURL(url);
  };

  return (
    <div style={{ padding: '24px', maxWidth: '1200px', margin: '0 auto' }}>
      <div style={{ marginBottom: '32px' }}>
        <h1 style={{ fontSize: '1.875rem', fontWeight: 600, color: '#1F2937', marginBottom: '8px' }}>Audit Trail</h1>
        <p style={{ color: '#6B7280', fontSize: '0.875rem' }}>Monitor user activity and system changes</p>
      </div>

      <StatusBanner loading={loading} error={error} onRetry={loadAuditLogs} loadingText="Loading audit trail…" />

      {loaded && (
        <>
          {/* Search and Filter Controls */}
          <div
            style={{
              display: 'flex',
              gap: '16px',
              marginBottom: '24px',
              flexWrap: 'wrap',
            }}
          >
            <div style={{ flex: 1, minWidth: '300px' }}>
              <div style={{ position: 'relative' }}>
                <Search
                  size={16}
                  style={{
                    position: 'absolute',
                    left: '12px',
                    top: '50%',
                    transform: 'translateY(-50%)',
                    color: '#9CA3AF',
                  }}
                />
                <input
                  type="text"
                  placeholder="Search by user, action, or details..."
                  value={searchTerm}
                  onChange={e => setSearchTerm(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '10px 12px 10px 40px',
                    border: '1px solid #E5E7EB',
                    borderRadius: '6px',
                    fontSize: '0.875rem',
                    outline: 'none',
                  }}
                />
              </div>
            </div>

            <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Filter size={16} color="#6B7280" />
                <select
                  value={filterAction}
                  onChange={e => setFilterAction(e.target.value as any)}
                  style={{
                    padding: '10px 12px',
                    border: '1px solid #E5E7EB',
                    borderRadius: '6px',
                    fontSize: '0.875rem',
                    background: '#FFFFFF',
                    cursor: 'pointer',
                  }}
                >
                  <option value="All">All Actions</option>
                  <option value="Created">Created</option>
                  <option value="Updated">Updated</option>
                  <option value="Deleted">Deleted</option>
                  <option value="Viewed">Viewed</option>
                </select>
              </div>

              <button
                onClick={handleExport}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  padding: '10px 16px',
                  background: '#1F5FA8',
                  color: '#FFFFFF',
                  border: 'none',
                  borderRadius: '6px',
                  fontSize: '0.875rem',
                  fontWeight: 500,
                  cursor: 'pointer',
                  transition: 'background 0.2s',
                }}
                onMouseEnter={e => (e.currentTarget.style.background = '#1E4A8C')}
                onMouseLeave={e => (e.currentTarget.style.background = '#1F5FA8')}
              >
                <Download size={16} />
                Export CSV
              </button>
            </div>
          </div>

          {/* Audit Logs Table */}
          <div
            style={{
              background: '#FFFFFF',
              border: '1px solid #E5E7EB',
              borderRadius: '8px',
              overflow: 'hidden',
            }}
          >
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ background: '#F9FAFB', borderBottom: '1px solid #E5E7EB' }}>
                    <th
                      style={{
                        padding: '12px 16px',
                        textAlign: 'left',
                        fontSize: '0.75rem',
                        fontWeight: 600,
                        color: '#6B7280',
                        textTransform: 'uppercase',
                        letterSpacing: '0.05em',
                      }}
                    >
                      ID
                    </th>
                    <th
                      style={{
                        padding: '12px 16px',
                        textAlign: 'left',
                        fontSize: '0.75rem',
                        fontWeight: 600,
                        color: '#6B7280',
                        textTransform: 'uppercase',
                        letterSpacing: '0.05em',
                      }}
                    >
                      User
                    </th>
                    <th
                      style={{
                        padding: '12px 16px',
                        textAlign: 'left',
                        fontSize: '0.75rem',
                        fontWeight: 600,
                        color: '#6B7280',
                        textTransform: 'uppercase',
                        letterSpacing: '0.05em',
                      }}
                    >
                      Action
                    </th>
                    <th
                      style={{
                        padding: '12px 16px',
                        textAlign: 'left',
                        fontSize: '0.75rem',
                        fontWeight: 600,
                        color: '#6B7280',
                        textTransform: 'uppercase',
                        letterSpacing: '0.05em',
                      }}
                    >
                      Details
                    </th>
                    <th
                      style={{
                        padding: '12px 16px',
                        textAlign: 'left',
                        fontSize: '0.75rem',
                        fontWeight: 600,
                        color: '#6B7280',
                        textTransform: 'uppercase',
                        letterSpacing: '0.05em',
                      }}
                    >
                      Timestamp
                    </th>
                    <th
                      style={{
                        padding: '12px 16px',
                        textAlign: 'left',
                        fontSize: '0.75rem',
                        fontWeight: 600,
                        color: '#6B7280',
                        textTransform: 'uppercase',
                        letterSpacing: '0.05em',
                      }}
                    >
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {filteredLogs.map((log, index) => (
                    <tr
                      key={log.id}
                      style={{
                        borderBottom: index < filteredLogs.length - 1 ? '1px solid #E5E7EB' : 'none',
                        transition: 'background 0.2s',
                      }}
                      onMouseEnter={e => (e.currentTarget.style.background = '#F9FAFB')}
                      onMouseLeave={e => (e.currentTarget.style.background = '#FFFFFF')}
                    >
                      <td style={{ padding: '12px 16px', fontSize: '0.875rem', color: '#1F2937' }}>#{log.id}</td>
                      <td style={{ padding: '12px 16px', fontSize: '0.875rem', color: '#1F2937' }}>{log.user}</td>
                      <td style={{ padding: '12px 16px' }}>
                        <AuditActionBadge action={log.action} />
                      </td>
                      <td style={{ padding: '12px 16px', fontSize: '0.875rem', color: '#4B5563' }}>{log.details}</td>
                      <td style={{ padding: '12px 16px', fontSize: '0.875rem', color: '#6B7280' }}>{log.timestamp}</td>
                      <td style={{ padding: '12px 16px' }}>
                        <button
                          onClick={() => setSelectedLog(log)}
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '6px',
                            padding: '6px 10px',
                            background: 'transparent',
                            border: '1px solid #E5E7EB',
                            borderRadius: '4px',
                            fontSize: '0.75rem',
                            color: '#6B7280',
                            cursor: 'pointer',
                            transition: 'all 0.2s',
                          }}
                          onMouseEnter={e => {
                            e.currentTarget.style.background = '#F3F4F6';
                            e.currentTarget.style.borderColor = '#D1D5DB';
                            e.currentTarget.style.color = '#1F2937';
                          }}
                          onMouseLeave={e => {
                            e.currentTarget.style.background = 'transparent';
                            e.currentTarget.style.borderColor = '#E5E7EB';
                            e.currentTarget.style.color = '#6B7280';
                          }}
                        >
                          <Eye size={14} />
                          View
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Detail Modal */}
          {selectedLog && (
            <div
              style={{
                position: 'fixed',
                top: 0,
                left: 0,
                right: 0,
                bottom: 0,
                background: 'rgba(0, 0, 0, 0.5)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                zIndex: 1000,
              }}
              onClick={() => setSelectedLog(null)}
            >
              <div
                style={{
                  background: '#FFFFFF',
                  borderRadius: '8px',
                  padding: '24px',
                  maxWidth: '500px',
                  width: '90%',
                  maxHeight: '80vh',
                  overflowY: 'auto',
                }}
                onClick={e => e.stopPropagation()}
              >
                <div style={{ marginBottom: '20px' }}>
                  <h2 style={{ fontSize: '1.25rem', fontWeight: 600, color: '#1F2937', marginBottom: '16px' }}>Audit Log Details</h2>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                    <div>
                      <label style={{ fontSize: '0.75rem', fontWeight: 600, color: '#6B7280', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Log ID</label>
                      <p style={{ margin: '4px 0 0 0', fontSize: '0.875rem', color: '#1F2937' }}>#{selectedLog.id}</p>
                    </div>

                    <div>
                      <label style={{ fontSize: '0.75rem', fontWeight: 600, color: '#6B7280', textTransform: 'uppercase', letterSpacing: '0.05em' }}>User</label>
                      <p style={{ margin: '4px 0 0 0', fontSize: '0.875rem', color: '#1F2937' }}>{selectedLog.user}</p>
                    </div>

                    <div>
                      <label style={{ fontSize: '0.75rem', fontWeight: 600, color: '#6B7280', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Action</label>
                      <div style={{ marginTop: '4px' }}>
                        <AuditActionBadge action={selectedLog.action} />
                      </div>
                    </div>

                    <div>
                      <label style={{ fontSize: '0.75rem', fontWeight: 600, color: '#6B7280', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Details</label>
                      <p style={{ margin: '4px 0 0 0', fontSize: '0.875rem', color: '#4B5563' }}>{selectedLog.details}</p>
                    </div>

                    {selectedLog.reportName && (
                      <div>
                        <label style={{ fontSize: '0.75rem', fontWeight: 600, color: '#6B7280', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Report Name</label>
                        <p style={{ margin: '4px 0 0 0', fontSize: '0.875rem', color: '#1F2937' }}>{selectedLog.reportName}</p>
                      </div>
                    )}

                    <div>
                      <label style={{ fontSize: '0.75rem', fontWeight: 600, color: '#6B7280', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Timestamp</label>
                      <p style={{ margin: '4px 0 0 0', fontSize: '0.875rem', color: '#6B7280' }}>{selectedLog.timestamp}</p>
                    </div>
                  </div>
                </div>

                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px' }}>
                  <button
                    onClick={() => setSelectedLog(null)}
                    style={{
                      padding: '8px 16px',
                      background: '#F3F4F6',
                      border: '1px solid #E5E7EB',
                      borderRadius: '6px',
                      fontSize: '0.875rem',
                      color: '#6B7280',
                      cursor: 'pointer',
                      transition: 'all 0.2s',
                    }}
                    onMouseEnter={e => {
                      e.currentTarget.style.background = '#E5E7EB';
                      e.currentTarget.style.color = '#4B5563';
                    }}
                    onMouseLeave={e => {
                      e.currentTarget.style.background = '#F3F4F6';
                      e.currentTarget.style.color = '#6B7280';
                    }}
                  >
                    Close
                  </button>
                </div>
              </div>
            </div>
          )}

          {filteredLogs.length === 0 && (
            <div
              style={{
                textAlign: 'center',
                padding: '60px 20px',
                color: '#9CA3AF',
                fontSize: '0.875rem',
              }}
            >
              No audit logs found matching your criteria.
            </div>
          )}
        </>
      )}
    </div>
  );
}
