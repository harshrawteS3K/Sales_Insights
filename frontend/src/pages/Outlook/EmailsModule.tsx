import { useState } from 'react';
import { Play, Eye, Loader2, Inbox, ArrowRight, Trash2 } from 'lucide-react';
import { useNavigate } from 'react-router';
import { BLUE, BORDER, RED } from '../../constants/theme';
import { ConfidenceBadge } from '../../components/ui/Badge';
import type { EmailRecord } from '../../types';
import { EmailsService } from '../../services/emails.service';
import { ApiError, getSession } from '../../api';

export function EmailsModule() {
  const navigate = useNavigate();
  const isAdmin = getSession()?.role === 'admin';
  const [extracting, setExtracting] = useState(false);
  const [extracted, setExtracted] = useState(false);
  const [emails, setEmails] = useState<EmailRecord[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<EmailRecord | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const refreshEmails = async () => {
    const data = await EmailsService.getExtractedEmails();
    setEmails(data);
    setExtracted(true);
  };

  const handleExtract = async () => {
    setExtracting(true);
    setExtracted(false);
    setError(null);
    setSyncMessage(null);
    try {
      if (isAdmin) {
        try {
          const sync = await EmailsService.triggerSync();
          setSyncMessage(sync.message || 'Outlook sync completed');
        } catch (syncErr) {
          const msg = syncErr instanceof ApiError ? syncErr.message : 'Outlook sync failed';
          setError(msg);
          setSyncMessage(null);
        }
      } else {
        setSyncMessage(
          'Signed in as user — loading email processing history only (admin required to sync Outlook).'
        );
      }
      await refreshEmails();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load email processing history');
      setExtracted(false);
    } finally {
      setExtracting(false);
    }
  };

  const openOutlook = (email: EmailRecord) => {
    window.location.href = `mailto:${email.senderEmail}`;
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    setDeleteBusy(true);
    setDeleteError(null);
    try {
      await EmailsService.deleteEmailRecord(deleteTarget.id);
      setDeleteTarget(null);
      await refreshEmails();
    } catch (err) {
      setDeleteError(err instanceof ApiError ? err.message : 'Failed to delete email record');
    } finally {
      setDeleteBusy(false);
    }
  };

  return (
    <div style={{ padding: '28px 32px', fontFamily: "'Inter', system-ui, sans-serif", maxWidth: 1200 }}>
      <div style={{ marginBottom: 28 }}>
        <h1 style={{ fontSize: '1.375rem', fontWeight: 700, color: '#111827', margin: 0, marginBottom: 4 }}>
          Distributor Email Extraction
        </h1>
        <p style={{ fontSize: '0.875rem', color: '#6B7280', margin: 0 }}>
          Sync Outlook attachments into Sales Insights. The table below is email processing history stored
          in this application — not a live view of your Outlook inbox.
        </p>
      </div>

      <div
        style={{
          background: 'white',
          border: `1px solid ${BORDER}`,
          borderRadius: 12,
          padding: '28px 32px',
          marginBottom: 24,
          boxShadow: '0 1px 4px rgba(0,0,0,0.04)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 24,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <div
            style={{
              width: 52,
              height: 52,
              borderRadius: 12,
              background: 'rgba(31,95,168,0.08)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <Inbox size={26} color={BLUE} />
          </div>
          <div>
            <div style={{ fontSize: '1rem', fontWeight: 700, color: '#111827', marginBottom: 3 }}>
              Email Processor
            </div>
            <div style={{ fontSize: '0.8125rem', color: '#6B7280' }}>
              Connects to Outlook via Microsoft Graph, downloads Excel attachments, and stores processing
              history for audit.
            </div>
          </div>
        </div>
        <button
          onClick={handleExtract}
          disabled={extracting}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            padding: '10px 24px',
            background: extracting ? '#9CA3AF' : BLUE,
            color: 'white',
            border: 'none',
            borderRadius: 8,
            fontSize: '0.875rem',
            fontWeight: 600,
            cursor: extracting ? 'not-allowed' : 'pointer',
            transition: 'background 0.15s',
            whiteSpace: 'nowrap',
            flexShrink: 0,
          }}
          onMouseEnter={e => {
            if (!extracting) e.currentTarget.style.background = '#1a4f8e';
          }}
          onMouseLeave={e => {
            if (!extracting) e.currentTarget.style.background = extracting ? '#9CA3AF' : BLUE;
          }}
        >
          {extracting ? (
            <Loader2 size={16} style={{ animation: 'spin 1s linear infinite' }} />
          ) : (
            <Play size={15} />
          )}
          {extracting ? 'Extracting…' : 'Extract Emails'}
        </button>
      </div>

      {error && (
        <div
          style={{
            padding: '12px 16px',
            background: 'rgba(217,58,47,0.06)',
            border: '1px solid rgba(217,58,47,0.25)',
            borderRadius: 8,
            marginBottom: 16,
            color: RED,
            fontSize: '0.875rem',
          }}
        >
          {error}
        </div>
      )}
      {syncMessage && !error && (
        <div
          style={{
            padding: '12px 16px',
            background: 'rgba(31,95,168,0.06)',
            border: '1px solid rgba(31,95,168,0.2)',
            borderRadius: 8,
            marginBottom: 16,
            color: BLUE,
            fontSize: '0.875rem',
          }}
        >
          {syncMessage}
        </div>
      )}

      {extracting && (
        <div
          style={{
            background: 'rgba(31,95,168,0.04)',
            border: '1px solid rgba(31,95,168,0.2)',
            borderRadius: 12,
            padding: '22px 28px',
            marginBottom: 24,
            display: 'flex',
            alignItems: 'center',
            gap: 14,
          }}
        >
          <Loader2 size={20} color={BLUE} style={{ animation: 'spin 1s linear infinite', flexShrink: 0 }} />
          <div>
            <div style={{ fontSize: '0.9375rem', fontWeight: 600, color: BLUE, marginBottom: 2 }}>
              Processing in Progress
            </div>
            <div style={{ fontSize: '0.8125rem', color: '#6B7280' }}>
              Syncing unread Outlook messages with Excel attachments and updating processing history…
            </div>
          </div>
        </div>
      )}

      {extracted && !extracting && (
        <>
          <div
            style={{
              background: 'white',
              border: `1px solid ${BORDER}`,
              borderRadius: 12,
              boxShadow: '0 1px 4px rgba(0,0,0,0.04)',
              overflow: 'hidden',
              marginBottom: 20,
            }}
          >
            <div style={{ padding: '16px 24px', borderBottom: `1px solid ${BORDER}` }}>
              <h2 style={{ fontSize: '0.9375rem', fontWeight: 700, color: '#111827', margin: 0 }}>
                Email Processing History {emails.length > 0 ? `(${emails.length})` : ''}
              </h2>
              <p style={{ margin: '6px 0 0', fontSize: '0.75rem', color: '#9CA3AF' }}>
                Stored in Sales Insights for auditing. Deleting a row removes history here only — the
                original Outlook message is not deleted.
              </p>
            </div>
            {emails.length === 0 ? (
              <div style={{ padding: '48px 24px', textAlign: 'center', color: '#9CA3AF', fontSize: '0.875rem' }}>
                No processing history yet. Run Extract Emails as admin after configuring Microsoft Graph.
              </div>
            ) : (
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ background: '#F9FAFB' }}>
                    {['Sender', 'Email Address', 'Subject', 'Date Received', 'Confidence Score', 'Action'].map(
                      col => (
                        <th
                          key={col}
                          style={{
                            padding: '11px 22px',
                            textAlign: 'left',
                            fontSize: '0.6875rem',
                            fontWeight: 700,
                            color: '#6B7280',
                            textTransform: 'uppercase',
                            letterSpacing: '0.055em',
                            borderBottom: `1px solid ${BORDER}`,
                            whiteSpace: 'nowrap',
                          }}
                        >
                          {col}
                        </th>
                      )
                    )}
                  </tr>
                </thead>
                <tbody>
                  {emails.map((email, idx) => (
                    <tr
                      key={email.id}
                      style={{
                        borderBottom: idx < emails.length - 1 ? `1px solid ${BORDER}` : 'none',
                        transition: 'background 0.1s',
                      }}
                      onMouseEnter={e => {
                        e.currentTarget.style.background = '#F9FAFB';
                      }}
                      onMouseLeave={e => {
                        e.currentTarget.style.background = 'white';
                      }}
                    >
                      <td style={{ padding: '18px 22px', fontSize: '0.9375rem', fontWeight: 700, color: '#111827' }}>
                        {email.senderName}
                      </td>
                      <td style={{ padding: '18px 22px', fontSize: '0.875rem', color: BLUE, fontWeight: 500 }}>
                        {email.senderEmail}
                      </td>
                      <td style={{ padding: '18px 22px', fontSize: '0.875rem', color: '#374151' }}>{email.subject}</td>
                      <td
                        style={{
                          padding: '18px 22px',
                          fontSize: '0.8125rem',
                          color: '#6B7280',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        {email.dateReceived}
                      </td>
                      <td style={{ padding: '18px 22px' }}>
                        <ConfidenceBadge score={email.confidenceScore} />
                      </td>
                      <td style={{ padding: '18px 22px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <button
                            type="button"
                            onClick={() => openOutlook(email)}
                            style={{
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: 6,
                              padding: '7px 16px',
                              background: 'rgba(31,95,168,0.07)',
                              color: BLUE,
                              border: '1px solid rgba(31,95,168,0.18)',
                              borderRadius: 7,
                              fontSize: '0.8125rem',
                              fontWeight: 600,
                              cursor: 'pointer',
                            }}
                          >
                            <Eye size={13} /> View
                          </button>
                          {isAdmin && (
                            <button
                              type="button"
                              onClick={() => {
                                setDeleteError(null);
                                setDeleteTarget(email);
                              }}
                              style={{
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: 6,
                                padding: '7px 16px',
                                background: 'rgba(220,38,38,0.04)',
                                color: '#DC2626',
                                border: '1px solid rgba(220,38,38,0.25)',
                                borderRadius: 7,
                                fontSize: '0.8125rem',
                                fontWeight: 600,
                                cursor: 'pointer',
                              }}
                            >
                              <Trash2 size={13} /> Delete
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
            <button
              type="button"
              onClick={() => navigate('/consolidated-data')}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 10,
                padding: '13px 28px',
                background: BLUE,
                color: 'white',
                border: 'none',
                borderRadius: 10,
                fontSize: '0.9375rem',
                fontWeight: 700,
                cursor: 'pointer',
                boxShadow: '0 4px 14px rgba(31,95,168,0.25)',
              }}
            >
              Proceed to Consolidated Data <ArrowRight size={17} />
            </button>
          </div>
        </>
      )}

      {!extracting && !extracted && (
        <div
          style={{
            background: 'white',
            border: `1px solid ${BORDER}`,
            borderRadius: 12,
            padding: '72px 32px',
            textAlign: 'center',
            boxShadow: '0 1px 4px rgba(0,0,0,0.04)',
          }}
        >
          <div
            style={{
              width: 64,
              height: 64,
              borderRadius: 16,
              background: 'rgba(31,95,168,0.07)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              margin: '0 auto 16px',
            }}
          >
            <Inbox size={28} color={BLUE} />
          </div>
          <div style={{ fontSize: '1rem', fontWeight: 700, color: '#374151', marginBottom: 8 }}>
            No processing history loaded
          </div>
          <div style={{ fontSize: '0.875rem', color: '#9CA3AF', marginBottom: 24 }}>
            Click Extract Emails to sync Outlook and load stored processing history.
          </div>
          <button
            type="button"
            onClick={handleExtract}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 8,
              padding: '10px 24px',
              background: BLUE,
              color: 'white',
              border: 'none',
              borderRadius: 8,
              fontSize: '0.875rem',
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            <Play size={15} /> Extract Emails
          </button>
        </div>
      )}

      {deleteTarget && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
          }}
          onClick={() => !deleteBusy && setDeleteTarget(null)}
        >
          <div
            style={{
              background: '#FFFFFF',
              borderRadius: 8,
              padding: 24,
              maxWidth: 460,
              width: '90%',
              boxShadow: '0 8px 30px rgba(0,0,0,0.18)',
            }}
            onClick={e => e.stopPropagation()}
          >
            <h2 style={{ fontSize: '1.125rem', fontWeight: 600, color: '#1F2937', margin: '0 0 12px' }}>
              Delete Email Record
            </h2>
            <p style={{ margin: '0 0 10px', fontSize: '0.875rem', color: '#374151', lineHeight: 1.55 }}>
              This removes the processed email history from Sales Insights.
            </p>
            <p style={{ margin: '0 0 16px', fontSize: '0.875rem', color: '#374151', lineHeight: 1.55 }}>
              The original Outlook email will remain in Outlook.
            </p>
            <p style={{ margin: '0 0 16px', fontSize: '0.8125rem', color: '#6B7280' }}>
              <strong style={{ color: '#111827' }}>{deleteTarget.subject}</strong>
              {' · '}
              {deleteTarget.senderEmail}
            </p>
            {deleteError && (
              <p style={{ color: '#DC2626', fontSize: '0.8125rem', marginBottom: 12 }}>{deleteError}</p>
            )}
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
              <button
                type="button"
                disabled={deleteBusy}
                onClick={() => setDeleteTarget(null)}
                style={{
                  padding: '8px 16px',
                  borderRadius: 7,
                  border: `1px solid ${BORDER}`,
                  background: 'white',
                  fontSize: '0.8125rem',
                  fontWeight: 600,
                  color: '#374151',
                  cursor: 'pointer',
                }}
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={deleteBusy}
                onClick={confirmDelete}
                style={{
                  padding: '8px 16px',
                  borderRadius: 7,
                  border: 'none',
                  background: '#DC2626',
                  fontSize: '0.8125rem',
                  fontWeight: 600,
                  color: 'white',
                  cursor: 'pointer',
                }}
              >
                {deleteBusy ? 'Deleting…' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}

      <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
