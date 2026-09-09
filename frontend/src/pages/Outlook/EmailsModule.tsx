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
import { DistributorService } from '../../services/distributor.service';

const QUARTERS = ['Q1 2026', 'Q2 2026', 'Q3 2026', 'Q4 2026', 'Q1 2027', 'Q2 2027'];

const MAP_OPTIONS = ['Customer Name', 'Product', 'Sales Quantity', 'Ignored'] as const;

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
      label: 'Not assessed',
      detail: 'Accuracy pending — refresh after Sync',
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
  const [distributorNameDraft, setDistributorNameDraft] = useState('');
  const [quarter, setQuarter] = useState('Q3 2026');
  const [fiscalYearStart, setFiscalYearStart] = useState(2025);
  const [importDone, setImportDone] = useState<string | null>(null);
  const [selectedEmailId, setSelectedEmailId] = useState<number | null>(null);
  const [consolidateOpen, setConsolidateOpen] = useState(false);
  const [consolidateBusy, setConsolidateBusy] = useState(false);
  const [consolidateError, setConsolidateError] = useState<string | null>(null);
  const [consolidatePreview, setConsolidatePreview] = useState<ERPPreviewResponse | null>(null);

  const refreshEmails = async () => {
    const data = await EmailsService.getExtractedEmails();
    setEmails(data);
  };

  useEffect(() => {
    refreshEmails().catch(() => undefined);
  }, []);

  const handleExtract = async () => {
    setExtracting(true);
    setError(null);
    setSyncMessage(null);
    try {
      if (isAdmin) {
        const sync = await EmailsService.triggerSync();
        setSyncMessage(sync.message || 'Outlook sync completed — review emails and Preview to import.');
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
        `Imported ${result.records_inserted} rows into Consolidated Data (${qLabel}).`,
      );
      await refreshEmails();
    } catch (err) {
      setPreviewError(err instanceof ApiError ? err.message : 'Import failed');
    } finally {
      setImportBusy(false);
    }
  };

  const targetEmailForConsolidate = useMemo(() => {
    if (selectedEmailId != null) {
      const found = emails.find(e => e.id === selectedEmailId);
      if (found?.hasExcel) return found;
    }
    return (
      emails.find(
        e =>
          e.hasExcel &&
          (e.statusLabel || '').toLowerCase() !== 'imported' &&
          (e.confidenceScore || 0) >= 75,
      ) ||
      emails.find(e => e.hasExcel && (e.statusLabel || '').toLowerCase() !== 'imported') ||
      emails.find(e => e.hasExcel) ||
      null
    );
  }, [emails, selectedEmailId]);

  const openConsolidate = async () => {
    setConsolidateError(null);
    const email = targetEmailForConsolidate;
    if (!email) {
      setError('No Excel email available to consolidate. Sync Outlook first.');
      return;
    }
    if ((email.confidenceScore || 0) > 0 && (email.confidenceScore || 0) < 75) {
      setError(
        `Accuracy is ${email.confidenceScore}% — review mappings in Preview before consolidating.`,
      );
      return;
    }
    setSelectedEmailId(email.id);
    setConsolidateOpen(true);
    setConsolidateBusy(true);
    setConsolidatePreview(null);
    try {
      const data = await EmailsService.previewEmail(email.id);
      setConsolidatePreview(data);
      setDistributorId(data.distributor_id ?? '');
      const matched =
        data.distributor_id != null
          ? (data.distributor_matches || data.all_distributors || []).find(
              d => d.id === data.distributor_id,
            )
          : null;
      setDistributorNameDraft(
        matched?.company ||
          matched?.name ||
          data.sender_name ||
          email.senderName ||
          email.senderEmail.split('@')[0] ||
          '',
      );
      if (data.fiscal_year_start) setFiscalYearStart(Number(data.fiscal_year_start));
      await refreshEmails();
    } catch (err) {
      setConsolidateError(err instanceof ApiError ? err.message : 'Failed to prepare workbook');
    } finally {
      setConsolidateBusy(false);
    }
  };

  const ensureDistributorId = async (): Promise<number> => {
    const email = targetEmailForConsolidate;
    if (!email) throw new Error('No email selected');
    const company =
      distributorNameDraft.trim() ||
      email.senderName?.trim() ||
      email.senderEmail.split('@')[0] ||
      'Unknown Distributor';

    if (distributorId) {
      const id = Number(distributorId);
      const selected = distributorOptions.find(d => d.id === id);
      const currentLabel = (selected?.company || selected?.name || '').trim();
      if (company && company !== currentLabel) {
        await DistributorService.update(id, { company, name: company });
      }
      return id;
    }

    // Do NOT attach sender mailbox email — identity is the typed distributor name.
    const created = await DistributorService.create({
      name: company,
      company,
      is_active: true,
    });
    setDistributorId(created.id);
    return created.id;
  };

  const proceedToConsolidation = async () => {
    const email = targetEmailForConsolidate;
    if (!email || !consolidatePreview) return;
    const accuracy = consolidatePreview.confidence?.overall ?? email.confidenceScore ?? 0;
    if (accuracy < 75) {
      setConsolidateError(
        `Accuracy is ${Math.round(accuracy)}%. Review column mappings in Preview before consolidating.`,
      );
      return;
    }
    if (!consolidatePreview.monthly_pivot && !quarter.trim()) {
      setConsolidateError('Select a reporting quarter');
      return;
    }
    if (!distributorNameDraft.trim() && !distributorId) {
      setConsolidateError('Enter a distributor name before importing');
      return;
    }
    setConsolidateBusy(true);
    setConsolidateError(null);
    try {
      const distId = await ensureDistributorId();
      const result = await EmailsService.importErp({
        email_id: email.id,
        distributor_id: distId,
        reporting_quarter: consolidatePreview.monthly_pivot
          ? `Q1 ${fiscalYearStart}`
          : quarter,
        fiscal_year_start: consolidatePreview.monthly_pivot ? fiscalYearStart : undefined,
        rows: consolidatePreview.rows,
      });
      setConsolidateOpen(false);
      const qLabel =
        result.quarters_imported?.length
          ? result.quarters_imported.join(', ')
          : result.reporting_quarter;
      setSyncMessage(
        `Imported ${result.records_inserted} rows for ${qLabel}. Opening Consolidated Data…`,
      );
      await refreshEmails();
      navigate('/consolidated-data');
    } catch (err) {
      setConsolidateError(err instanceof ApiError ? err.message : 'Consolidation import failed');
    } finally {
      setConsolidateBusy(false);
    }
  };

  const distributorOptions = useMemo(() => {
    const matches = (consolidatePreview || preview)?.distributor_matches || [];
    const all = (consolidatePreview || preview)?.all_distributors || [];
    if (matches.length > 1) return matches;
    if (matches.length === 1 && !(consolidatePreview || preview)?.distributor_unknown) return matches;
    return all.length ? all : matches;
  }, [preview, consolidatePreview]);

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
          onClick={() => void openConsolidate()}
          style={btnPrimary}
          disabled={!targetEmailForConsolidate || consolidateBusy}
        >
          {consolidateBusy && consolidateOpen ? <Loader2 size={15} /> : null}
          Proceed to consolidation
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
              Downloads Excel only — import happens after you Preview and Approve.
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
              setConsolidatePreview(null);
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
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
              <h2 style={{ margin: 0, fontSize: '1.125rem', fontWeight: 700, color: '#111827' }}>
                Proceed to consolidation
              </h2>
              <button
                type="button"
                style={{ border: 'none', background: 'transparent', cursor: 'pointer' }}
                onClick={() => {
                  if (!consolidateBusy) {
                    setConsolidateOpen(false);
                    setConsolidatePreview(null);
                  }
                }}
              >
                <X size={18} />
              </button>
            </div>
            <p style={{ margin: '0 0 16px', fontSize: '0.875rem', color: '#6B7280' }}>
              Import all extracted rows into Consolidated Data (Customer, Product, Sales Quantity),
              then open that tab.
            </p>

            {consolidateBusy && !consolidatePreview ? (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: BLUE, marginBottom: 12 }}>
                <Loader2 size={16} /> Preparing workbook…
              </div>
            ) : null}

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

            {consolidatePreview && (
              <>
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '1fr 1fr',
                    gap: 10,
                    marginBottom: 14,
                    padding: 12,
                    background: '#F9FAFB',
                    borderRadius: 8,
                    border: `1px solid ${BORDER}`,
                  }}
                >
                  <Info label="Workbook" value={consolidatePreview.workbook_name || '—'} />
                  <Info
                    label="Accuracy"
                    value={`${Math.round(consolidatePreview.confidence?.overall || 0)}%`}
                    valueColor={confColor(consolidatePreview.confidence?.overall || 0)}
                  />
                  <Info label="Rows to import" value={String(consolidatePreview.row_count)} />
                  <Info label="Sheet" value={consolidatePreview.sheet_name || '—'} />
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginBottom: 16 }}>
                  <div>
                    <label style={labelStyle}>Distributor name</label>
                    <input
                      value={distributorNameDraft}
                      onChange={e => {
                        setDistributorNameDraft(e.target.value);
                        // Typing a custom name = create/update path; clear forced pick
                        if (!e.target.value.trim()) setDistributorId('');
                      }}
                      placeholder="Enter distributor company name"
                      style={{
                        ...selectStyle,
                        width: '100%',
                      }}
                    />
                    <div style={{ fontSize: '0.75rem', color: '#6B7280', marginTop: 6 }}>
                      {distributorId
                        ? 'Linked to an existing distributor — name will be updated on import if you change it.'
                        : 'No match yet — a new distributor will be created with this name.'}
                    </div>
                  </div>
                  {distributorOptions.length > 0 && (
                    <div>
                      <label style={labelStyle}>Or pick existing distributor</label>
                      <select
                        value={distributorId}
                        onChange={e => {
                          const id = e.target.value ? Number(e.target.value) : '';
                          setDistributorId(id);
                          if (id) {
                            const opt = distributorOptions.find(d => d.id === id);
                            if (opt) setDistributorNameDraft(opt.company || opt.name || '');
                          }
                        }}
                        style={selectStyle}
                      >
                        <option value="">Create new from name above</option>
                        {distributorOptions.map(d => (
                          <option key={d.id} value={d.id}>
                            {d.company}
                            {d.email ? ` (${d.email})` : ''}
                          </option>
                        ))}
                      </select>
                    </div>
                  )}
                  <div style={{ flex: '0 1 180px', maxWidth: 280 }}>
                    <label style={labelStyle}>
                      {consolidatePreview.monthly_pivot
                        ? 'Fiscal Year Start (Apr)'
                        : 'Reporting Quarter'}
                    </label>
                    {consolidatePreview.monthly_pivot ? (
                      <select
                        value={fiscalYearStart}
                        onChange={e => setFiscalYearStart(Number(e.target.value))}
                        style={selectStyle}
                      >
                        {[2024, 2025, 2026, 2027].map(y => (
                          <option key={y} value={y}>
                            FY {y}-{String(y + 1).slice(-2)}
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
              </>
            )}

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
              <button
                type="button"
                style={btnSecondary}
                disabled={consolidateBusy}
                onClick={() => {
                  setConsolidateOpen(false);
                  setConsolidatePreview(null);
                }}
              >
                Cancel
              </button>
              <button
                type="button"
                style={{
                  ...btnPrimary,
                  background:
                    consolidatePreview && (consolidatePreview.confidence?.overall || 0) >= 75
                      ? BLUE
                      : '#9CA3AF',
                }}
                disabled={
                  consolidateBusy ||
                  !consolidatePreview ||
                  (consolidatePreview.confidence?.overall || 0) < 75
                }
                onClick={() => void proceedToConsolidation()}
              >
                {consolidateBusy ? 'Importing…' : 'Import & open Consolidated'}
              </button>
            </div>
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
