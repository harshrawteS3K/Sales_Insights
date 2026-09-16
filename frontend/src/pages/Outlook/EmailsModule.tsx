import { useEffect, useMemo, useState, type CSSProperties } from 'react';
import {
  Play,
  Eye,
  Loader2,
  Inbox,
  ArrowRight,
  Trash2,
  X,
  CheckCircle2,
} from 'lucide-react';
import { useNavigate } from 'react-router';
import { BLUE, BORDER, RED, TEAL } from '../../constants/theme';
import type { EmailRecord } from '../../types';
import {
  EmailsService,
  type ERPMappingItem,
  type ERPPreviewResponse,
} from '../../services/emails.service';
import { ApiError, getSession } from '../../api';
import { isAdminRole } from '../../utils/rbac';

const QUARTERS = ['Q1 2026', 'Q2 2026', 'Q3 2026', 'Q4 2026', 'Q1 2027', 'Q2 2027'];

const MAP_OPTIONS = ['Customer Name', 'Product', 'Sales Quantity', 'Ignored'] as const;

/** Max unread emails per Sync Outlook click; max ready emails per Proceed batch. */
const BATCH_LIMIT = 5;
const MIN_IMPORT_ACCURACY = 75;

type BatchItemResult = {
  emailId: number;
  subject: string;
  status: 'ok' | 'failed' | 'skipped';
  detail: string;
  rows?: number;
};

function confColor(score: number): string {
  if (score >= 90) return '#059669';
  if (score >= 75) return '#B45309';
  return RED;
}

/** Single Accuracy badge (mapping quality for the full workbook). */
function accuracyMeta(score?: number | null): {
  label: string;
  detail: string;
  bg: string;
  color: string;
} {
  const value = score ?? 0;
  if (value <= 0) {
    return {
      label: 'Scoring…',
      detail: 'Background job running — refresh in a few seconds',
      bg: 'rgba(107,114,128,0.12)',
      color: '#4B5563',
    };
  }
  if (value >= 90) {
    return {
      label: `${value}% Accuracy`,
      detail: 'Mapped correctly across the workbook',
      bg: 'rgba(5,150,105,0.12)',
      color: '#059669',
    };
  }
  if (value >= 75) {
    return {
      label: `${value}% Accuracy`,
      detail: 'Acceptable — review mappings if needed',
      bg: 'rgba(245,158,11,0.15)',
      color: '#B45309',
    };
  }
  return {
    label: `${value}% Accuracy`,
    detail: 'Low — fix column mappings before import',
    bg: 'rgba(220,38,38,0.12)',
    color: RED,
  };
}

const btnPrimary: CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 6,
  padding: '8px 14px',
  border: 'none',
  borderRadius: 8,
  background: BLUE,
  color: 'white',
  fontSize: '0.8125rem',
  fontWeight: 600,
  cursor: 'pointer',
};

const btnSecondary: CSSProperties = {
  ...btnPrimary,
  background: 'white',
  color: '#374151',
  border: `1px solid ${BORDER}`,
};

export function EmailsModule() {
  const navigate = useNavigate();
  const isAdmin = isAdminRole(getSession()?.role);
  const [extracting, setExtracting] = useState(false);
  const [emails, setEmails] = useState<EmailRecord[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);

  const [previewEmail, setPreviewEmail] = useState<EmailRecord | null>(null);
  const [preview, setPreview] = useState<ERPPreviewResponse | null>(null);
  const [previewBusy, setPreviewBusy] = useState(false);
  const [importBusy, setImportBusy] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [mappings, setMappings] = useState<ERPMappingItem[]>([]);
  const [distributorId, setDistributorId] = useState<number | ''>('');
  const [quarter, setQuarter] = useState('Q3 2026');
  const [fiscalYearStart, setFiscalYearStart] = useState(2025);
  const [importDone, setImportDone] = useState<string | null>(null);
  const [selectedEmailId, setSelectedEmailId] = useState<number | null>(null);
  const [consolidateOpen, setConsolidateOpen] = useState(false);
  const [consolidateBusy, setConsolidateBusy] = useState(false);
  const [consolidateError, setConsolidateError] = useState<string | null>(null);
  const [batchProgress, setBatchProgress] = useState<{
    current: number;
    total: number;
    label: string;
  } | null>(null);
  const [batchResults, setBatchResults] = useState<BatchItemResult[]>([]);

  const refreshEmails = async () => {
    const data = await EmailsService.getExtractedEmails();
    setEmails(data);
    setSelectedEmailId(prev =>
      prev != null && data.some(e => e.id === prev) ? prev : null,
    );
  };

  useEffect(() => {
    refreshEmails().catch(() => undefined);
  }, []);

  // While any email is still scoring (confidence 0), poll so Accuracy updates without manual refresh.
  useEffect(() => {
    const pending = emails.some(e => !e.confidenceScore || e.confidenceScore <= 0);
    if (!pending) return undefined;
    const id = window.setInterval(() => {
      refreshEmails().catch(() => undefined);
    }, 4000);
    return () => window.clearInterval(id);
  }, [emails]);

  const handleExtract = async () => {
    setExtracting(true);
    setError(null);
    setSyncMessage(null);
    try {
      if (isAdmin) {
        const sync = await EmailsService.triggerSync();
        setSyncMessage(
          sync.message ||
            `Outlook sync completed (max ${BATCH_LIMIT} unread). Review Accuracy, then Proceed to consolidation.`,
        );
      } else {
        setSyncMessage('Signed in as user — loading history only (admin required to sync).');
      }
      await refreshEmails();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to sync / load emails');
    } finally {
      setExtracting(false);
    }
  };

  const openPreview = async (email: EmailRecord) => {
    setPreviewEmail(email);
    setPreview(null);
    setPreviewError(null);
    setImportDone(null);
    setPreviewBusy(true);
    try {
      const data = await EmailsService.previewEmail(email.id);
      setPreview(data);
      setMappings(data.mapping || []);
      setDistributorId(data.distributor_id ?? '');
      if (data.fiscal_year_start) setFiscalYearStart(Number(data.fiscal_year_start));
      await refreshEmails();
    } catch (err) {
      setPreviewError(err instanceof ApiError ? err.message : 'Failed to parse workbook');
    } finally {
      setPreviewBusy(false);
    }
  };

  const recomputeWithMappings = async (next: ERPMappingItem[]) => {
    if (!previewEmail) return;
    setMappings(next);
    setPreviewBusy(true);
    setPreviewError(null);
    try {
      const data = await EmailsService.previewEmail(previewEmail.id, next);
      setPreview(data);
      setMappings(data.mapping || next);
      if (data.distributor_id && !distributorId) {
        setDistributorId(data.distributor_id);
      }
    } catch (err) {
      setPreviewError(err instanceof ApiError ? err.message : 'Failed to recompute mapping');
    } finally {
      setPreviewBusy(false);
    }
  };

  const onChangeMapped = (index: number, mapped: string) => {
    const next = mappings.map((m, i) => (i === index ? { ...m, mapped } : m));
    // Prevent duplicate target fields (except Ignored)
    if (mapped !== 'Ignored') {
      for (let i = 0; i < next.length; i++) {
        if (i !== index && next[i].mapped === mapped) {
          next[i] = { ...next[i], mapped: 'Ignored' };
        }
      }
    }
    void recomputeWithMappings(next);
  };

  const onChangeColumn = (index: number, column: number) => {
    const colMeta = preview?.available_columns?.find(c => c.column === column);
    const next = mappings.map((m, i) =>
      i === index
        ? {
            ...m,
            column,
            original: colMeta?.header || m.original,
          }
        : m,
    );
    void recomputeWithMappings(next);
  };

  const overall = preview?.confidence?.overall ?? 0;
  const canImport =
    overall >= 75 &&
    Boolean(distributorId) &&
    (preview?.monthly_pivot ? Boolean(fiscalYearStart) : Boolean(quarter)) &&
    !previewBusy;

  const approveImport = async () => {
    if (!previewEmail || !preview || !distributorId) return;
    setImportBusy(true);
    setPreviewError(null);
    try {
      const result = await EmailsService.importErp({
        email_id: previewEmail.id,
        distributor_id: Number(distributorId),
        reporting_quarter: preview.monthly_pivot
          ? `Q1 ${fiscalYearStart}`
          : quarter,
        fiscal_year_start: preview.monthly_pivot ? fiscalYearStart : undefined,
        mapping: mappings,
        rows: preview.rows,
      });
      const qLabel =
        result.quarters_imported?.length
          ? result.quarters_imported.join(', ')
          : result.reporting_quarter;
      setImportDone(
        `Imported ${result.records_inserted} rows` +
          (result.workbooks_imported && result.workbooks_imported.length > 1
            ? ` from ${result.workbooks_imported.length} workbooks`
            : '') +
          ` into Consolidated Data (${qLabel}).`,
      );
      await refreshEmails();
    } catch (err) {
      setPreviewError(err instanceof ApiError ? err.message : 'Import failed');
    } finally {
      setImportBusy(false);
    }
  };

  const readyEmailsForBatch = useMemo(() => {
    return emails
      .filter(
        e =>
          e.hasExcel &&
          (e.statusLabel || '').toLowerCase() !== 'imported' &&
          (e.statusLabel || '').toLowerCase() !== 'failed' &&
          (e.confidenceScore || 0) >= MIN_IMPORT_ACCURACY,
      )
      .slice(0, BATCH_LIMIT);
  }, [emails]);

  const pendingLowAccuracyCount = useMemo(
    () =>
      emails.filter(
        e =>
          e.hasExcel &&
          (e.statusLabel || '').toLowerCase() !== 'imported' &&
          (e.confidenceScore || 0) > 0 &&
          (e.confidenceScore || 0) < MIN_IMPORT_ACCURACY,
      ).length,
    [emails],
  );

  const resolveDistributorId = (data: ERPPreviewResponse): number | null => {
    if (data.distributor_id != null) return Number(data.distributor_id);
    const matches = data.distributor_matches || [];
    if (matches.length === 1 && !data.distributor_unknown) return Number(matches[0].id);
    return null;
  };

  const resolveReportingQuarter = (
    data: ERPPreviewResponse,
  ): { reporting_quarter: string; fiscal_year_start?: number } => {
    if (data.monthly_pivot) {
      const fy = Number(data.fiscal_year_start || fiscalYearStart || 2025);
      return { reporting_quarter: `Q1 ${fy}`, fiscal_year_start: fy };
    }
    const fromRow = (data.rows || [])
      .map(r => (r.period || r.reporting_quarter || '').trim())
      .find(Boolean);
    if (fromRow) return { reporting_quarter: fromRow };
    return { reporting_quarter: quarter.trim() || 'Q1 2026' };
  };

  const runBatchConsolidate = async () => {
    setConsolidateError(null);
    setBatchResults([]);
    setError(null);

    const batch = readyEmailsForBatch;
    if (!batch.length) {
      if (pendingLowAccuracyCount > 0) {
        setError(
          `${pendingLowAccuracyCount} email(s) need Preview (accuracy < ${MIN_IMPORT_ACCURACY}%). Fix mappings there before consolidating.`,
        );
      } else {
        setError(
          `No ready emails to consolidate (need Excel + accuracy ≥ ${MIN_IMPORT_ACCURACY}%). Sync Outlook or wait for scoring.`,
        );
      }
      return;
    }

    setConsolidateOpen(true);
    setConsolidateBusy(true);
    setBatchProgress({ current: 0, total: batch.length, label: 'Starting…' });

    const results: BatchItemResult[] = [];
    let totalRows = 0;

    try {
      for (let i = 0; i < batch.length; i++) {
        const email = batch[i];
        setBatchProgress({
          current: i + 1,
          total: batch.length,
          label: email.subject || email.senderEmail || `Email #${email.id}`,
        });
        try {
          const data = await EmailsService.previewEmail(
            email.id,
            undefined,
            fiscalYearStart || undefined,
          );
          const accuracy = data.confidence?.overall ?? email.confidenceScore ?? 0;
          if (accuracy < MIN_IMPORT_ACCURACY) {
            results.push({
              emailId: email.id,
              subject: email.subject,
              status: 'skipped',
              detail: `Accuracy ${Math.round(accuracy)}% — use Preview`,
            });
            setBatchResults([...results]);
            continue;
          }
          const distId = resolveDistributorId(data);
          if (distId == null) {
            results.push({
              emailId: email.id,
              subject: email.subject,
              status: 'skipped',
              detail: 'Distributor not matched — use Preview to map',
            });
            setBatchResults([...results]);
            continue;
          }
          if (data.fiscal_year_start) setFiscalYearStart(Number(data.fiscal_year_start));
          const periodArgs = resolveReportingQuarter(data);
          const result = await EmailsService.importErp({
            email_id: email.id,
            distributor_id: distId,
            reporting_quarter: periodArgs.reporting_quarter,
            fiscal_year_start: periodArgs.fiscal_year_start,
            rows: data.rows,
          });
          totalRows += result.records_inserted || 0;
          const qLabel =
            result.quarters_imported?.length
              ? result.quarters_imported.join(', ')
              : result.reporting_quarter;
          const wbCount = result.workbooks_imported?.length || 1;
          const skipN = result.workbook_skips?.length || 0;
          results.push({
            emailId: email.id,
            subject: email.subject,
            status: 'ok',
            detail: `${result.records_inserted} rows / ${wbCount} workbook(s)${
              skipN ? `, ${skipN} skipped` : ''
            } (${qLabel})`,
            rows: result.records_inserted,
          });
        } catch (err) {
          results.push({
            emailId: email.id,
            subject: email.subject,
            status: 'failed',
            detail: err instanceof ApiError ? err.message : 'Import failed',
          });
        }
        setBatchResults([...results]);
      }

      const refreshed = await EmailsService.getExtractedEmails();
      setEmails(refreshed);
      setSelectedEmailId(prev =>
        prev != null && refreshed.some(e => e.id === prev) ? prev : null,
      );

      const ok = results.filter(r => r.status === 'ok').length;
      const skipped = results.filter(r => r.status === 'skipped').length;
      const failed = results.filter(r => r.status === 'failed').length;
      const stillReady = refreshed.filter(
        e =>
          e.hasExcel &&
          (e.statusLabel || '').toLowerCase() !== 'imported' &&
          (e.statusLabel || '').toLowerCase() !== 'failed' &&
          (e.confidenceScore || 0) >= MIN_IMPORT_ACCURACY,
      ).length;

      setSyncMessage(
        `Batch consolidate: ${ok} imported (${totalRows} rows), ${skipped} skipped, ${failed} failed.` +
          (stillReady > 0
            ? ` ${stillReady} ready left — click Proceed again (max ${BATCH_LIMIT}).`
            : '') +
          (ok > 0 ? ' Opening Consolidated Data…' : ''),
      );
      setBatchProgress(null);
      if (ok > 0) {
        window.setTimeout(() => {
          setConsolidateOpen(false);
          navigate('/consolidated-data');
        }, 1100);
      } else {
        setConsolidateError(
          'No emails were imported. Fix skipped items via Preview, then try again.',
        );
      }
    } finally {
      setConsolidateBusy(false);
      setBatchProgress(null);
    }
  };

  const distributorOptions = useMemo(() => {
    const matches = preview?.distributor_matches || [];
    const all = preview?.all_distributors || [];
    if (matches.length > 1) return matches;
    if (matches.length === 1 && !preview?.distributor_unknown) return matches;
    return all.length ? all : matches;
  }, [preview]);

  return (
    <div style={{ padding: '28px 32px', fontFamily: "'Inter', system-ui, sans-serif", maxWidth: 1200 }}>
      <div
        style={{
          marginBottom: 28,
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          gap: 16,
          flexWrap: 'wrap',
        }}
      >
        <div>
          <h1 style={{ fontSize: '1.375rem', fontWeight: 700, color: '#111827', margin: '0 0 4px' }}>
            Email Extraction
          </h1>
          <p style={{ fontSize: '0.875rem', color: '#6B7280', margin: 0 }}>
            Sync Outlook ERP Excel attachments, preview AI column mapping, then approve import into
            Consolidated Data.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void runBatchConsolidate()}
          style={btnPrimary}
          disabled={consolidateBusy || (!readyEmailsForBatch.length && !emails.some(e => e.hasExcel))}
          title={
            readyEmailsForBatch.length
              ? `Import up to ${BATCH_LIMIT} ready emails (accuracy ≥ ${MIN_IMPORT_ACCURACY}%)`
              : `Need Excel emails with accuracy ≥ ${MIN_IMPORT_ACCURACY}%`
          }
        >
          {consolidateBusy ? <Loader2 size={15} className="spin" /> : null}
          Proceed to consolidation
          {readyEmailsForBatch.length > 0 ? ` (${Math.min(readyEmailsForBatch.length, BATCH_LIMIT)})` : ''}
          <ArrowRight size={15} />
        </button>
      </div>

      <div
        style={{
          background: 'white',
          border: `1px solid ${BORDER}`,
          borderRadius: 12,
          padding: '24px 28px',
          marginBottom: 24,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 24,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <div
            style={{
              width: 48,
              height: 48,
              borderRadius: 12,
              background: 'rgba(31,95,168,0.08)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <Inbox size={24} color={BLUE} />
          </div>
          <div>
            <div style={{ fontWeight: 700, color: '#111827' }}>Outlook Sync</div>
            <div style={{ fontSize: '0.8125rem', color: '#6B7280' }}>
              Pulls up to {BATCH_LIMIT} unread Excel emails per sync. Import with Proceed (batch of{' '}
              {BATCH_LIMIT}).
            </div>
          </div>
        </div>
        <button type="button" onClick={handleExtract} disabled={extracting} style={btnPrimary}>
          {extracting ? <Loader2 size={16} className="spin" /> : <Play size={15} />}
          {extracting ? 'Syncing…' : 'Sync Outlook'}
        </button>
      </div>

      {error && (
        <div
          style={{
            padding: 12,
            marginBottom: 16,
            borderRadius: 8,
            background: 'rgba(217,58,47,0.06)',
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
            padding: 12,
            marginBottom: 16,
            borderRadius: 8,
            background: 'rgba(16,185,129,0.08)',
            color: '#065F46',
            fontSize: '0.875rem',
          }}
        >
          {syncMessage}
        </div>
      )}

      <div style={{ background: 'white', border: `1px solid ${BORDER}`, borderRadius: 12, overflow: 'hidden' }}>
        {emails.length === 0 ? (
          <div style={{ padding: 48, textAlign: 'center', color: '#9CA3AF' }}>
            No emails yet. Click Sync Outlook to download ERP attachments.
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
              <thead>
                <tr style={{ background: '#F9FAFB', borderBottom: `1px solid ${BORDER}` }}>
                  {['Sender', 'Subject', 'Received', 'Excel', 'Accuracy', 'Actions'].map(h => (
                    <th
                      key={h}
                      style={{
                        textAlign: 'left',
                        padding: '12px 14px',
                        fontSize: '0.6875rem',
                        fontWeight: 700,
                        color: '#6B7280',
                        textTransform: 'uppercase',
                        letterSpacing: '0.04em',
                      }}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {emails.map(email => {
                  const acc = accuracyMeta(email.confidenceScore);
                  const selected = selectedEmailId === email.id;
                  return (
                    <tr
                      key={email.id}
                      onClick={() => setSelectedEmailId(email.id)}
                      style={{
                        borderBottom: `1px solid ${BORDER}`,
                        background: selected ? 'rgba(31,95,168,0.06)' : undefined,
                        cursor: 'pointer',
                      }}
                    >
                      <td style={{ padding: '12px 14px', color: '#374151' }}>
                        <div>{email.senderName}</div>
                        <div style={{ fontSize: '0.75rem', color: '#9CA3AF' }}>{email.senderEmail}</div>
                      </td>
                      <td style={{ padding: '12px 14px', color: '#374151', maxWidth: 240 }}>
                        {email.subject}
                      </td>
                      <td style={{ padding: '12px 14px', color: '#6B7280', whiteSpace: 'nowrap' }}>
                        {email.dateReceived}
                      </td>
                      <td style={{ padding: '12px 14px', color: '#374151' }}>
                        {email.attachmentName || '—'}
                      </td>
                      <td style={{ padding: '12px 14px' }}>
                        <div
                          title={acc.detail}
                          style={{
                            display: 'inline-flex',
                            flexDirection: 'column',
                            gap: 2,
                            padding: '5px 10px',
                            borderRadius: 8,
                            background: acc.bg,
                            color: acc.color,
                            maxWidth: 200,
                          }}
                        >
                          <span style={{ fontSize: '0.75rem', fontWeight: 700 }}>{acc.label}</span>
                          <span style={{ fontSize: '0.6875rem', fontWeight: 500, opacity: 0.9 }}>
                            {acc.detail}
                          </span>
                        </div>
                      </td>
                      <td style={{ padding: '12px 14px' }}>
                        <div style={{ display: 'flex', gap: 6, flexWrap: 'nowrap' }}>
                          <button
                            type="button"
                            style={{ ...btnSecondary, padding: '5px 8px', fontSize: '0.75rem' }}
                            disabled={!email.hasExcel || !isAdmin}
                            onClick={() => void openPreview(email)}
                          >
                            <Eye size={12} /> Preview
                          </button>
                          {isAdmin && (
                            <button
                              type="button"
                              style={{
                                ...btnSecondary,
                                padding: '5px 8px',
                                fontSize: '0.75rem',
                                color: RED,
                              }}
                              onClick={async () => {
                                await EmailsService.deleteEmailRecord(email.id);
                                await refreshEmails();
                              }}
                            >
                              <Trash2 size={12} />
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {(previewEmail || previewBusy) && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(15,23,42,0.45)',
            zIndex: 1000,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: 16,
          }}
          onClick={() => {
            if (!previewBusy && !importBusy) {
              setPreviewEmail(null);
              setPreview(null);
            }
          }}
        >
          <div
            style={{
              background: 'white',
              borderRadius: 12,
              width: '100%',
              maxWidth: 920,
              maxHeight: '92vh',
              overflowY: 'auto',
              padding: 24,
              boxShadow: '0 20px 40px rgba(0,0,0,0.15)',
            }}
            onClick={e => e.stopPropagation()}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
              <h2 style={{ margin: 0, fontSize: '1.125rem', fontWeight: 700 }}>AI Mapping Preview</h2>
              <button
                type="button"
                onClick={() => {
                  setPreviewEmail(null);
                  setPreview(null);
                }}
                style={{ border: 'none', background: 'transparent', cursor: 'pointer', color: '#6B7280' }}
              >
                <X size={18} />
              </button>
            </div>

            {previewBusy && !preview && (
              <div style={{ padding: 40, textAlign: 'center', color: '#6B7280' }}>
                <Loader2 size={22} style={{ marginBottom: 8 }} /> Parsing workbook…
              </div>
            )}

            {previewError && (
              <div
                style={{
                  padding: 12,
                  marginBottom: 12,
                  borderRadius: 8,
                  background: 'rgba(217,58,47,0.08)',
                  color: RED,
                  fontSize: '0.8125rem',
                }}
              >
                {previewError}
              </div>
            )}

            {importDone && (
              <div
                style={{
                  padding: 12,
                  marginBottom: 12,
                  borderRadius: 8,
                  background: 'rgba(16,185,129,0.1)',
                  color: '#065F46',
                  fontSize: '0.875rem',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                }}
              >
                <CheckCircle2 size={16} /> {importDone}
              </div>
            )}

            {preview && (
              <>
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
                    gap: 12,
                    marginBottom: 16,
                    padding: 14,
                    background: '#F9FAFB',
                    borderRadius: 8,
                    border: `1px solid ${BORDER}`,
                  }}
                >
                  <Info label="Workbook" value={preview.workbook_name || '—'} />
                  <Info label="Sheet" value={preview.sheet_name} />
                  <Info label="Total Rows" value={String(preview.row_count)} />
                  <Info
                    label="Mapping Source"
                    value={
                      preview.mapping_source === 'llm'
                        ? 'LLM Assisted'
                        : preview.mapping_source === 'manual'
                          ? 'Manual'
                          : 'Python'
                    }
                    valueColor={preview.mapping_source === 'llm' ? '#1D4ED8' : '#111827'}
                  />
                  <Info
                    label="Overall Confidence"
                    value={`${Math.round(overall)}%`}
                    valueColor={confColor(overall)}
                  />
                </div>

                {overall < 75 && (
                  <div
                    style={{
                      padding: 12,
                      marginBottom: 14,
                      borderRadius: 8,
                      background: 'rgba(220,38,38,0.08)',
                      color: RED,
                      fontSize: '0.8125rem',
                    }}
                  >
                    Low accuracy detected. Please review column mappings before importing.
                  </div>
                )}

                <div style={{ fontSize: '0.75rem', fontWeight: 700, color: '#6B7280', marginBottom: 8 }}>
                  COLUMN MAPPING
                </div>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8125rem', marginBottom: 16 }}>
                  <thead>
                    <tr style={{ background: '#F3F4F6' }}>
                      <th style={th}>Original Column</th>
                      <th style={th}>AI Mapping</th>
                      <th style={th}>Accuracy</th>
                    </tr>
                  </thead>
                  <tbody>
                    {mappings.map((m, idx) => (
                      <tr key={`${m.original}-${idx}`} style={{ borderBottom: `1px solid ${BORDER}` }}>
                        <td style={td}>
                          <select
                            value={m.column ?? ''}
                            onChange={e => onChangeColumn(idx, Number(e.target.value))}
                            style={selectStyle}
                            disabled={previewBusy}
                          >
                            {(preview.available_columns || []).map(c => (
                              <option key={c.column} value={c.column}>
                                {c.header}
                              </option>
                            ))}
                            {!preview.available_columns?.length && (
                              <option value={m.column ?? ''}>{m.original}</option>
                            )}
                          </select>
                        </td>
                        <td style={td}>
                          <select
                            value={m.mapped}
                            onChange={e => onChangeMapped(idx, e.target.value)}
                            style={selectStyle}
                            disabled={previewBusy}
                          >
                            {MAP_OPTIONS.map(opt => (
                              <option key={opt} value={opt}>
                                {opt}
                              </option>
                            ))}
                          </select>
                        </td>
                        <td style={{ ...td, fontWeight: 700, color: confColor(m.confidence || 0) }}>
                          {Math.round(m.confidence || 0)}%
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>

                <div style={{ display: 'flex', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
                  <div style={{ flex: '1 1 220px' }}>
                    <label style={labelStyle}>Distributor</label>
                    <select
                      value={distributorId}
                      onChange={e =>
                        setDistributorId(e.target.value ? Number(e.target.value) : '')
                      }
                      style={selectStyle}
                    >
                      <option value="">
                        {preview.distributor_unknown ? 'Unknown Distributor — select…' : 'Select distributor'}
                      </option>
                      {distributorOptions.map(d => (
                        <option key={d.id} value={d.id}>
                          {d.company}
                          {d.email ? ` (${d.email})` : ''}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div style={{ flex: '0 1 180px' }}>
                    <label style={labelStyle}>
                      {preview.monthly_pivot ? 'Fiscal Year Start (Apr)' : 'Reporting Quarter'}
                    </label>
                    {preview.monthly_pivot ? (
                      <select
                        value={fiscalYearStart}
                        onChange={e => {
                          const y = Number(e.target.value);
                          setFiscalYearStart(y);
                          if (previewEmail) {
                            setPreviewBusy(true);
                            EmailsService.previewEmail(previewEmail.id, mappings, y)
                              .then(data => {
                                setPreview(data);
                                setMappings(data.mapping || mappings);
                              })
                              .catch(err =>
                                setPreviewError(
                                  err instanceof ApiError ? err.message : 'Failed to refresh quarters',
                                ),
                              )
                              .finally(() => setPreviewBusy(false));
                          }
                        }}
                        style={selectStyle}
                      >
                        {[2024, 2025, 2026, 2027].map(y => (
                          <option key={y} value={y}>
                            FY {y}-{String(y + 1).slice(-2)} (Q1–Q4 {y})
                          </option>
                        ))}
                      </select>
                    ) : (
                      <select
                        value={quarter}
                        onChange={e => setQuarter(e.target.value)}
                        style={selectStyle}
                      >
                        {QUARTERS.map(q => (
                          <option key={q} value={q}>
                            {q}
                          </option>
                        ))}
                      </select>
                    )}
                  </div>
                </div>

                {preview.monthly_pivot && (
                  <div
                    style={{
                      padding: 10,
                      marginBottom: 14,
                      borderRadius: 8,
                      background: 'rgba(31,95,168,0.06)',
                      color: BLUE,
                      fontSize: '0.8125rem',
                    }}
                  >
                    Monthly columns are split into quarterly totals (Q1=Apr–Jun … Q4=Jan–Mar) for
                    Consolidated Data.
                  </div>
                )}

                <div style={{ fontSize: '0.75rem', fontWeight: 700, color: '#6B7280', marginBottom: 8 }}>
                  NORMALIZED ROWS
                </div>
                <div style={{ maxHeight: 240, overflow: 'auto', marginBottom: 16, border: `1px solid ${BORDER}`, borderRadius: 8 }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8125rem' }}>
                    <thead>
                      <tr style={{ background: '#F3F4F6' }}>
                        <th style={th}>Sr No</th>
                        {preview.monthly_pivot && <th style={th}>Quarter</th>}
                        <th style={th}>Customer</th>
                        <th style={th}>Product</th>
                        <th style={{ ...th, textAlign: 'right' }}>Sales Qty</th>
                      </tr>
                    </thead>
                    <tbody>
                      {preview.rows.map((r, i) => (
                        <tr key={`${r.customer_name}-${r.period || ''}-${i}`} style={{ borderBottom: `1px solid ${BORDER}` }}>
                          <td style={td}>{i + 1}</td>
                          {preview.monthly_pivot && <td style={td}>{r.period || '—'}</td>}
                          <td style={td}>{r.customer_name}</td>
                          <td style={td}>{r.product}</td>
                          <td style={{ ...td, textAlign: 'right' }}>{r.sales_quantity}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
                  <button
                    type="button"
                    style={btnSecondary}
                    onClick={() => {
                      setPreviewEmail(null);
                      setPreview(null);
                    }}
                  >
                    Close
                  </button>
                  {!importDone && (
                    <button
                      type="button"
                      style={{
                        ...btnPrimary,
                        background: canImport ? TEAL : '#9CA3AF',
                        cursor: canImport && !importBusy ? 'pointer' : 'not-allowed',
                      }}
                      disabled={!canImport || importBusy}
                      onClick={() => void approveImport()}
                    >
                      {importBusy ? 'Importing…' : 'Approve Import'}
                    </button>
                  )}
                  {importDone && (
                    <button
                      type="button"
                      style={{ ...btnPrimary, background: TEAL }}
                      onClick={() => navigate('/consolidated-data')}
                    >
                      Open Consolidated Data
                    </button>
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {consolidateOpen && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(15,23,42,0.45)',
            zIndex: 1000,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: 16,
          }}
          onClick={() => {
            if (!consolidateBusy) {
              setConsolidateOpen(false);
              setBatchResults([]);
              setConsolidateError(null);
            }
          }}
        >
          <div
            style={{
              background: 'white',
              borderRadius: 12,
              width: '100%',
              maxWidth: 520,
              padding: 24,
              boxShadow: '0 20px 50px rgba(0,0,0,0.2)',
            }}
            onClick={e => e.stopPropagation()}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: 12,
              }}
            >
              <h2 style={{ margin: 0, fontSize: '1.125rem', fontWeight: 700, color: '#111827' }}>
                Batch consolidation
              </h2>
              <button
                type="button"
                style={{ border: 'none', background: 'transparent', cursor: consolidateBusy ? 'default' : 'pointer' }}
                disabled={consolidateBusy}
                onClick={() => {
                  setConsolidateOpen(false);
                  setBatchResults([]);
                  setConsolidateError(null);
                }}
              >
                <X size={18} />
              </button>
            </div>
            <p style={{ margin: '0 0 16px', fontSize: '0.875rem', color: '#6B7280' }}>
              Importing up to {BATCH_LIMIT} ready emails (Excel + accuracy ≥ {MIN_IMPORT_ACCURACY}% +
              matched distributor). Others stay for Preview.
            </p>

            {batchProgress && (
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 10,
                  color: BLUE,
                  marginBottom: 14,
                  fontSize: '0.875rem',
                  fontWeight: 600,
                }}
              >
                <Loader2 size={16} className="spin" />
                Importing {batchProgress.current}/{batchProgress.total}: {batchProgress.label}
              </div>
            )}

            {consolidateError && (
              <div
                style={{
                  padding: 12,
                  marginBottom: 12,
                  borderRadius: 8,
                  background: 'rgba(217,58,47,0.08)',
                  color: RED,
                  fontSize: '0.8125rem',
                }}
              >
                {consolidateError}
              </div>
            )}

            {batchResults.length > 0 && (
              <div
                style={{
                  maxHeight: 260,
                  overflow: 'auto',
                  border: `1px solid ${BORDER}`,
                  borderRadius: 8,
                  marginBottom: 14,
                }}
              >
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8125rem' }}>
                  <thead>
                    <tr style={{ background: '#F3F4F6' }}>
                      <th style={th}>Email</th>
                      <th style={th}>Status</th>
                      <th style={th}>Detail</th>
                    </tr>
                  </thead>
                  <tbody>
                    {batchResults.map(r => (
                      <tr key={r.emailId} style={{ borderBottom: `1px solid ${BORDER}` }}>
                        <td style={{ ...td, maxWidth: 160 }}>{r.subject || `#${r.emailId}`}</td>
                        <td
                          style={{
                            ...td,
                            fontWeight: 700,
                            color:
                              r.status === 'ok'
                                ? '#059669'
                                : r.status === 'skipped'
                                  ? '#B45309'
                                  : RED,
                          }}
                        >
                          {r.status}
                        </td>
                        <td style={td}>{r.detail}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {!consolidateBusy && (
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
                <button
                  type="button"
                  style={btnSecondary}
                  onClick={() => {
                    setConsolidateOpen(false);
                    setBatchResults([]);
                    setConsolidateError(null);
                  }}
                >
                  Close
                </button>
                {batchResults.some(r => r.status === 'ok') && (
                  <button
                    type="button"
                    style={btnPrimary}
                    onClick={() => {
                      setConsolidateOpen(false);
                      navigate('/consolidated-data');
                    }}
                  >
                    Open Consolidated Data
                  </button>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function Info({
  label,
  value,
  valueColor,
}: {
  label: string;
  value: string;
  valueColor?: string;
}) {
  return (
    <div>
      <div style={{ fontSize: '0.6875rem', color: '#6B7280', fontWeight: 600, marginBottom: 4 }}>
        {label}
      </div>
      <div style={{ fontSize: '0.875rem', fontWeight: 700, color: valueColor || '#111827' }}>{value}</div>
    </div>
  );
}

const th: CSSProperties = {
  textAlign: 'left',
  padding: '8px 10px',
  fontSize: '0.6875rem',
  fontWeight: 700,
  color: '#6B7280',
};

const td: CSSProperties = {
  padding: '8px 10px',
  color: '#374151',
  verticalAlign: 'middle',
};

const labelStyle: CSSProperties = {
  display: 'block',
  fontSize: '0.75rem',
  fontWeight: 600,
  color: '#374151',
  marginBottom: 6,
};

const selectStyle: CSSProperties = {
  width: '100%',
  padding: '8px 10px',
  borderRadius: 8,
  border: `1px solid ${BORDER}`,
  fontSize: '0.8125rem',
  fontFamily: 'inherit',
};
