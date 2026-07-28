import { useState, useEffect } from 'react';
import { useLayoutContext } from '../../hooks/useLayoutContext';
import { Upload, Download, Eye, MessageSquare, FileText } from 'lucide-react';
import type { Report, ChatMessage } from '../../types';
import { ReportsService } from '../../services/reports.service';
import { BLUE } from '../../constants/theme';
import { ApiError } from '../../api';
import { StatusBanner } from '../../components/common/StatusBanner';

export function ExistingReports() {
  const { userRole } = useLayoutContext();
  const [activeView, setActiveView] = useState<'list' | 'chat'>('list');
  const [reports, setReports] = useState<Report[]>([]);

  const [loaded, setLoaded] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadSuccess, setUploadSuccess] = useState<string | null>(null);
  const [filterOpts, setFilterOpts] = useState<{ products: string[]; applications: string[] }>({ products: [], applications: [] });
  const [suggestedQuestions, setSuggestedQuestions] = useState<string[]>([]);

  const [selectedFilters, setSelectedFilters] = useState<{
    products: string[];
    applications: string[];
  }>({
    products: [],
    applications: [],
  });

  const [selectedReport, setSelectedReport] = useState<string>('');
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatInput, setChatInput] = useState('');

  const loadReports = async () => {
    setLoading(true);
    setError(null);
    try {
      const [rpts, opts, questions] = await Promise.all([
        ReportsService.getReports(),
        ReportsService.getFilterCategories(),
        ReportsService.getSuggestedQuestions(),
      ]);
      setReports(rpts);
      setFilterOpts(opts);
      setSuggestedQuestions(questions);
      setLoaded(true);
    } catch (err) {
      setLoaded(false);
      setError(err instanceof ApiError ? err.message : 'Failed to load reports');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadReports();
  }, []);

  const filteredReports = reports.filter(report => {
    const productMatch =
      selectedFilters.products.length === 0 ||
      selectedFilters.products.some(filter => report.categories.products.includes(filter));
    const applicationMatch =
      selectedFilters.applications.length === 0 ||
      selectedFilters.applications.some(filter => report.categories.applications.includes(filter));

    return productMatch && applicationMatch;
  });

  const handleFilterToggle = (category: 'products' | 'applications', value: string) => {
    setSelectedFilters(prev => ({
      ...prev,
      [category]: prev[category].includes(value)
        ? prev[category].filter(item => item !== value)
        : [...prev[category], value],
    }));
  };

  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;

    const ext = file.name.slice(file.name.lastIndexOf('.')).toLowerCase();
    if (ext !== '.xlsx' && ext !== '.xlsm') {
      setUploadError('Only .xlsx and .xlsm files are accepted');
      setUploadSuccess(null);
      return;
    }

    if (userRole !== 'admin') {
      setUploadError('Admin role is required to upload reports');
      setUploadSuccess(null);
      return;
    }

    setUploadError(null);
    setUploadSuccess(null);
    setUploadProgress(0);
    try {
      const result = await ReportsService.uploadReport(file, setUploadProgress);
      setUploadSuccess(result.message || 'Report uploaded successfully');
      await loadReports();
    } catch (err) {
      setUploadError(err instanceof ApiError ? err.message : 'Upload failed');
    } finally {
      setUploadProgress(null);
    }
  };

  const handleSendMessage = () => {
    if (chatInput.trim()) {
      const userMessage: ChatMessage = {
        id: Date.now().toString(),
        type: 'user',
        content: chatInput,
        timestamp: new Date(),
      };

      setChatMessages(prev => [...prev, userMessage]);
      setChatInput('');

      const assistantMessage: ChatMessage = {
        id: (Date.now() + 1).toString(),
        type: 'assistant',
        content:
          'Report Q&A is not connected to a backend AI service in Phase 1. Suggested questions and report metadata are loaded from the API; conversational analysis will be available in a later phase.',
        timestamp: new Date(),
      };
      setChatMessages(prev => [...prev, assistantMessage]);
    }
  };

  return (
    <div style={{ padding: '24px', maxWidth: '1200px', margin: '0 auto' }}>
      <div style={{ marginBottom: '32px' }}>
        <h1 style={{ fontSize: '1.875rem', fontWeight: 600, color: '#1F2937', marginBottom: '8px' }}>Existing Reports</h1>
        <p style={{ color: '#6B7280', fontSize: '0.875rem' }}>Access and analyze your market research reports</p>
      </div>

      <StatusBanner loading={loading} error={error} onRetry={loadReports} loadingText="Loading reports…" />

      {uploadError && (
        <div style={{ marginBottom: 16, padding: '10px 14px', background: 'rgba(217,58,47,0.06)', borderRadius: 8, color: '#D93A2F', fontSize: '0.875rem' }}>
          {uploadError}
        </div>
      )}
      {uploadSuccess && (
        <div style={{ marginBottom: 16, padding: '10px 14px', background: 'rgba(16,185,129,0.08)', borderRadius: 8, color: '#059669', fontSize: '0.875rem' }}>
          {uploadSuccess}
        </div>
      )}
      {uploadProgress !== null && (
        <div style={{ marginBottom: 16, fontSize: '0.875rem', color: BLUE, fontWeight: 600 }}>
          Uploading… {uploadProgress}%
        </div>
      )}

      {loaded && (
        <>
          {/* Action Cards */}
          <div style={{ display: 'flex', gap: '16px', marginBottom: '32px' }}>
            <button
              onClick={() => setActiveView('list')}
              style={{
                flex: 1,
                padding: '20px',
                background: activeView === 'list' ? '#1F5FA8' : '#FFFFFF',
                border: `1px solid ${activeView === 'list' ? '#1F5FA8' : '#E5E7EB'}`,
                borderRadius: '8px',
                textAlign: 'left',
                cursor: 'pointer',
                transition: 'all 0.2s',
              }}
              onMouseEnter={e => {
                if (activeView !== 'list') {
                  e.currentTarget.style.background = '#F9FAFB';
                  e.currentTarget.style.borderColor = '#D1D5DB';
                }
              }}
              onMouseLeave={e => {
                if (activeView !== 'list') {
                  e.currentTarget.style.background = '#FFFFFF';
                  e.currentTarget.style.borderColor = '#E5E7EB';
                }
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
                <FileText size={20} color={activeView === 'list' ? '#FFFFFF' : '#1F5FA8'} />
                <h3
                  style={{
                    fontSize: '1rem',
                    fontWeight: 600,
                    color: activeView === 'list' ? '#FFFFFF' : '#1F2937',
                    margin: 0,
                  }}
                >
                  Reports List
                </h3>
              </div>
              <p
                style={{
                  fontSize: '0.875rem',
                  color: activeView === 'list' ? '#E5E7EB' : '#6B7280',
                  margin: 0,
                }}
              >
                View and manage reports
              </p>
            </button>

            <button
              onClick={() => setActiveView('chat')}
              style={{
                flex: 1,
                padding: '20px',
                background: activeView === 'chat' ? '#1F5FA8' : '#FFFFFF',
                border: `1px solid ${activeView === 'chat' ? '#1F5FA8' : '#E5E7EB'}`,
                borderRadius: '8px',
                textAlign: 'left',
                cursor: 'pointer',
                transition: 'all 0.2s',
              }}
              onMouseEnter={e => {
                if (activeView !== 'chat') {
                  e.currentTarget.style.background = '#F9FAFB';
                  e.currentTarget.style.borderColor = '#D1D5DB';
                }
              }}
              onMouseLeave={e => {
                if (activeView !== 'chat') {
                  e.currentTarget.style.background = '#FFFFFF';
                  e.currentTarget.style.borderColor = '#E5E7EB';
                }
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
                <MessageSquare size={20} color={activeView === 'chat' ? '#FFFFFF' : '#1F5FA8'} />
                <h3
                  style={{
                    fontSize: '1rem',
                    fontWeight: 600,
                    color: activeView === 'chat' ? '#FFFFFF' : '#1F2937',
                    margin: 0,
                  }}
                >
                  Chat with Data
                </h3>
              </div>
              <p
                style={{
                  fontSize: '0.875rem',
                  color: activeView === 'chat' ? '#E5E7EB' : '#6B7280',
                  margin: 0,
                }}
              >
                Query report data conversationally
              </p>
            </button>
          </div>

          {/* Content Area */}
          {activeView === 'list' && (
            <div style={{ display: 'flex', gap: '24px' }}>
              {/* Filter Sidebar */}
              <div style={{ width: '280px', flexShrink: 0 }}>
                <div
                  style={{
                    background: '#FFFFFF',
                    border: '1px solid #E5E7EB',
                    borderRadius: '8px',
                    padding: '20px',
                  }}
                >
                  <h3 style={{ fontSize: '1rem', fontWeight: 600, color: '#1F2937', marginBottom: '16px' }}>Filters</h3>

                  {/* Products Section */}
                  <div style={{ marginBottom: '24px' }}>
                    <h4 style={{ fontSize: '0.875rem', fontWeight: 600, color: '#374151', marginBottom: '12px' }}>Synthetic Rubber</h4>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                      {filterOpts.products.map(product => (
                        <label
                          key={product}
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '8px',
                            cursor: 'pointer',
                            fontSize: '0.75rem',
                            color: '#4B5563',
                          }}
                        >
                          <input
                            type="checkbox"
                            checked={selectedFilters.products.includes(product)}
                            onChange={() => handleFilterToggle('products', product)}
                            style={{
                              width: '14px',
                              height: '14px',
                              accentColor: '#1F5FA8',
                            }}
                          />
                          {product}
                        </label>
                      ))}
                    </div>
                  </div>

                  {/* Applications Section */}
                  <div style={{ marginBottom: '24px' }}>
                    <h4 style={{ fontSize: '0.875rem', fontWeight: 600, color: '#374151', marginBottom: '12px' }}>Applications / Industries</h4>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                      {filterOpts.applications.map(application => (
                        <label
                          key={application}
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '8px',
                            cursor: 'pointer',
                            fontSize: '0.75rem',
                            color: '#4B5563',
                          }}
                        >
                          <input
                            type="checkbox"
                            checked={selectedFilters.applications.includes(application)}
                            onChange={() => handleFilterToggle('applications', application)}
                            style={{
                              width: '14px',
                              height: '14px',
                              accentColor: '#1F5FA8',
                            }}
                          />
                          {application}
                        </label>
                      ))}
                    </div>
                  </div>

                  {/* Clear Filters Button */}
                  <button
                    onClick={() => setSelectedFilters({ products: [], applications: [] })}
                    style={{
                      width: '100%',
                      padding: '8px 12px',
                      background: '#F3F4F6',
                      border: '1px solid #E5E7EB',
                      borderRadius: '4px',
                      fontSize: '0.75rem',
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
                    Clear Filters
                  </button>
                </div>
              </div>

              {/* Main Content */}
              <div style={{ flex: 1 }}>
                {/* Upload Button */}
                <div style={{ marginBottom: '24px' }}>
                  <label
                    htmlFor="file-upload"
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '8px',
                      padding: '10px 16px',
                      background: '#1F5FA8',
                      color: '#FFFFFF',
                      borderRadius: '6px',
                      cursor: 'pointer',
                      fontSize: '0.875rem',
                      fontWeight: 500,
                      transition: 'background 0.2s',
                    }}
                    onMouseEnter={e => (e.currentTarget.style.background = '#1E4A8C')}
                    onMouseLeave={e => (e.currentTarget.style.background = '#1F5FA8')}
                  >
                    <Upload size={16} />
                    Upload Report
                  </label>
                  <input id="file-upload" type="file" accept=".xlsx,.xlsm" onChange={handleFileUpload} style={{ display: 'none' }} />
                </div>

                {/* Filter Status */}
                {(selectedFilters.products.length > 0 || selectedFilters.applications.length > 0) && (
                  <div
                    style={{
                      marginBottom: '16px',
                      padding: '8px 12px',
                      background: '#F0F9FF',
                      border: '1px solid #BFDBFE',
                      borderRadius: '4px',
                    }}
                  >
                    <span style={{ fontSize: '0.75rem', color: '#1E40AF' }}>
                      Showing {filteredReports.length} of {reports.length} reports
                    </span>
                  </div>
                )}

                {/* Reports Grid */}
                <div style={{ display: 'grid', gap: '16px' }}>
                  {filteredReports.map(report => (
                    <div
                      key={report.id}
                      style={{
                        background: '#FFFFFF',
                        border: '1px solid #E5E7EB',
                        borderRadius: '8px',
                        padding: '20px',
                        transition: 'box-shadow 0.2s',
                      }}
                      onMouseEnter={e => (e.currentTarget.style.boxShadow = '0 4px 6px rgba(0, 0, 0, 0.1)')}
                      onMouseLeave={e => (e.currentTarget.style.boxShadow = 'none')}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', marginBottom: '12px' }}>
                        <div>
                          <h3 style={{ fontSize: '1.125rem', fontWeight: 600, color: '#1F2937', marginBottom: '4px' }}>{report.name}</h3>
                          <div style={{ display: 'flex', gap: '12px', fontSize: '0.875rem', color: '#6B7280' }}>
                            <span>{report.date}</span>
                            <span>•</span>
                            <span>{report.type}</span>
                          </div>
                          <div style={{ marginTop: '8px', display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                            {report.categories.products.map(product => (
                              <span
                                key={product}
                                style={{
                                  padding: '2px 6px',
                                  background: '#EBF8FF',
                                  color: '#1E40AF',
                                  fontSize: '0.625rem',
                                  borderRadius: '3px',
                                  border: '1px solid #BFDBFE',
                                }}
                              >
                                {product}
                              </span>
                            ))}
                            {report.categories.applications.map(application => (
                              <span
                                key={application}
                                style={{
                                  padding: '2px 6px',
                                  background: '#F0FDF4',
                                  color: '#166534',
                                  fontSize: '0.625rem',
                                  borderRadius: '3px',
                                  border: '1px solid #BBF7D0',
                                }}
                              >
                                {application}
                              </span>
                            ))}
                          </div>
                        </div>
                        <div style={{ display: 'flex', gap: '8px' }}>
                          <button
                            style={{
                              padding: '6px',
                              background: 'transparent',
                              border: '1px solid #E5E7EB',
                              borderRadius: '4px',
                              cursor: 'pointer',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              transition: 'all 0.2s',
                            }}
                            onMouseEnter={e => {
                              e.currentTarget.style.background = '#F3F4F6';
                              e.currentTarget.style.borderColor = '#D1D5DB';
                            }}
                            onMouseLeave={e => {
                              e.currentTarget.style.background = 'transparent';
                              e.currentTarget.style.borderColor = '#E5E7EB';
                            }}
                            title="View Report"
                          >
                            <Eye size={16} color="#6B7280" />
                          </button>
                          <button
                            style={{
                              padding: '6px',
                              background: 'transparent',
                              border: '1px solid #E5E7EB',
                              borderRadius: '4px',
                              cursor: 'pointer',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              transition: 'all 0.2s',
                            }}
                            onMouseEnter={e => {
                              e.currentTarget.style.background = '#F3F4F6';
                              e.currentTarget.style.borderColor = '#D1D5DB';
                            }}
                            onMouseLeave={e => {
                              e.currentTarget.style.background = 'transparent';
                              e.currentTarget.style.borderColor = '#E5E7EB';
                            }}
                            title="Download Report"
                          >
                            <Download size={16} color="#6B7280" />
                          </button>
                        </div>
                      </div>
                      <p style={{ color: '#4B5563', fontSize: '0.875rem', lineHeight: 1.5, margin: 0 }}>{report.description}</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {activeView === 'chat' && (
            <div style={{ height: '600px', display: 'flex', flexDirection: 'column' }}>
              {/* Report Selection */}
              <div style={{ marginBottom: '16px' }}>
                <label style={{ fontSize: '0.875rem', fontWeight: 500, color: '#374151', marginBottom: '8px', display: 'block' }}>
                  Select Report to Chat With:
                </label>
                <select
                  value={selectedReport}
                  onChange={e => setSelectedReport(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '10px 12px',
                    border: '1px solid #E5E7EB',
                    borderRadius: '6px',
                    fontSize: '0.875rem',
                    background: '#FFFFFF',
                    cursor: 'pointer',
                    outline: 'none',
                  }}
                >
                  <option value="">All Reports</option>
                  {reports.map(report => (
                    <option key={report.id} value={report.id}>
                      {report.name} - {report.date}
                    </option>
                  ))}
                </select>
              </div>

              {/* Chat Messages */}
              <div
                style={{
                  flex: 1,
                  background: '#FFFFFF',
                  border: '1px solid #E5E7EB',
                  borderRadius: '8px',
                  padding: '20px',
                  overflowY: 'auto',
                  marginBottom: '16px',
                }}
              >
                {chatMessages.length === 0 ? (
                  <div
                    style={{
                      textAlign: 'center',
                      color: '#9CA3AF',
                      fontSize: '0.875rem',
                      marginTop: '100px',
                    }}
                  >
                    {selectedReport
                      ? `Start a conversation about ${reports.find(r => r.id === selectedReport)?.name}`
                      : 'Start a conversation about your report data'}
                  </div>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                    {chatMessages.map(message => (
                      <div
                        key={message.id}
                        style={{
                          display: 'flex',
                          justifyContent: message.type === 'user' ? 'flex-end' : 'flex-start',
                        }}
                      >
                        <div
                          style={{
                            maxWidth: '70%',
                            padding: '12px 16px',
                            borderRadius: '8px',
                            background: message.type === 'user' ? '#1F5FA8' : '#F3F4F6',
                            color: message.type === 'user' ? '#FFFFFF' : '#1F2937',
                          }}
                        >
                          <p style={{ margin: 0, fontSize: '0.875rem', lineHeight: 1.5 }}>{message.content}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Chat Input */}
              <div style={{ display: 'flex', gap: '12px' }}>
                <input
                  type="text"
                  value={chatInput}
                  onChange={e => setChatInput(e.target.value)}
                  onKeyPress={e => e.key === 'Enter' && handleSendMessage()}
                  placeholder={
                    selectedReport
                      ? `Ask about ${reports.find(r => r.id === selectedReport)?.name}...`
                      : 'Ask about your reports...'
                  }
                  style={{
                    flex: 1,
                    padding: '12px 16px',
                    border: '1px solid #E5E7EB',
                    borderRadius: '6px',
                    fontSize: '0.875rem',
                    outline: 'none',
                  }}
                />
                <button
                  onClick={handleSendMessage}
                  style={{
                    padding: '12px 24px',
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
                  Send
                </button>
              </div>

              {/* Suggested Questions */}
              {chatMessages.length === 0 && (
                <div style={{ marginTop: '16px' }}>
                  <p style={{ fontSize: '0.75rem', color: '#6B7280', marginBottom: '8px' }}>Suggested questions:</p>
                  <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                    {suggestedQuestions.map(suggestion => (
                      <button
                        key={suggestion}
                        onClick={() => setChatInput(suggestion)}
                        style={{
                          padding: '6px 12px',
                          background: '#F3F4F6',
                          border: '1px solid #E5E7EB',
                          borderRadius: '4px',
                          fontSize: '0.75rem',
                          color: '#4B5563',
                          cursor: 'pointer',
                          transition: 'all 0.2s',
                        }}
                        onMouseEnter={e => {
                          e.currentTarget.style.background = '#E5E7EB';
                          e.currentTarget.style.borderColor = '#D1D5DB';
                        }}
                        onMouseLeave={e => {
                          e.currentTarget.style.background = '#F3F4F6';
                          e.currentTarget.style.borderColor = '#E5E7EB';
                        }}
                      >
                        {suggestion}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
