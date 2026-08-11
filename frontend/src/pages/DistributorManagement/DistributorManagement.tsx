import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type FormEvent,
} from 'react';
import {
  Search,
  Plus,
  Pencil,
  Users,
  UserX,
  Mail,
  X,
} from 'lucide-react';
import { Navigate } from 'react-router';
import { useLayoutContext } from '../../hooks/useLayoutContext';
import { StatusBanner } from '../../components/common/StatusBanner';
import {
  DistributorService,
  type BulkEmailDraftJobStatus,
} from '../../services/distributor.service';
import { ApiError } from '../../api';
import { BLUE, BORDER, RED, TEAL } from '../../constants/theme';
import { isAdminRole } from '../../utils/rbac';
import type { Distributor, DistributorCreatePayload } from '../../types';

const inputStyle: CSSProperties = {
  width: '100%',
  padding: '9px 12px',
  fontSize: '0.875rem',
  border: `1px solid ${BORDER}`,
  borderRadius: 8,
  outline: 'none',
  fontFamily: 'inherit',
};

const labelStyle: CSSProperties = {
  display: 'block',
  fontSize: '0.75rem',
  fontWeight: 600,
  color: '#374151',
  marginBottom: 6,
};

const primaryBtn: CSSProperties = {
  padding: '9px 16px',
  fontSize: '0.8125rem',
  fontWeight: 600,
  border: 'none',
  borderRadius: 8,
  background: BLUE,
  color: 'white',
  cursor: 'pointer',
};

const secondaryBtn: CSSProperties = {
  padding: '9px 16px',
  fontSize: '0.8125rem',
  fontWeight: 600,
  border: `1px solid ${BORDER}`,
  borderRadius: 8,
  background: 'white',
  color: '#374151',
  cursor: 'pointer',
};

const QUARTER_OPTIONS = ['Q1 2026', 'Q2 2026', 'Q3 2026', 'Q4 2026'];

function StatusBadge({ active }: { active: boolean }) {
  return (
    <span
      style={{
        display: 'inline-flex',
        padding: '3px 10px',
        borderRadius: 999,
        fontSize: '0.6875rem',
        fontWeight: 700,
        color: active ? '#059669' : '#DC2626',
        background: active ? 'rgba(5,150,105,0.1)' : 'rgba(220,38,38,0.1)',
        textTransform: 'uppercase',
        letterSpacing: '0.04em',
      }}
    >
      {active ? 'Active' : 'Inactive'}
    </span>
  );
}

type DialogMode =
  | 'create'
  | 'edit'
  | 'customers'
  | 'package'
  | 'deactivate'
  | 'bulkConfirm'
  | 'bulkProgress'
  | null;

type FormState = {
  name: string;
  company: string;
  code: string;
  contact_person: string;
  email: string;
  cc_email: string;
  is_active: boolean;
};

const emptyForm = (): FormState => ({
  name: '',
  company: '',
  code: '',
  contact_person: '',
  email: '',
  cc_email: '',
  is_active: true,
});

function formFromDistributor(d: Distributor): FormState {
  return {
    name: d.name || '',
    company: d.company || '',
    code: d.code || '',
    contact_person: d.contact_person || '',
    email: d.email || '',
    cc_email: d.cc_email || '',
    is_active: d.is_active,
  };
}

function toPayload(form: FormState): DistributorCreatePayload {
  return {
    name: form.name.trim(),
    company: form.company.trim(),
    code: form.code.trim() || null,
    contact_person: form.contact_person.trim() || null,
    email: form.email.trim() || null,
    cc_email: form.cc_email.trim() || null,
    is_active: form.is_active,
  };
}

export function DistributorManagement() {
  const { userRole } = useLayoutContext();
  const [rows, setRows] = useState<Distributor[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchInput, setSearchInput] = useState('');
  const [search, setSearch] = useState('');

  const [dialog, setDialog] = useState<DialogMode>(null);
  const [target, setTarget] = useState<Distributor | null>(null);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [form, setForm] = useState<FormState>(emptyForm);

  const [customers, setCustomers] = useState<string[]>([]);
  const [customersLoading, setCustomersLoading] = useState(false);
  const [reportingQuarter, setReportingQuarter] = useState('');
  const [draftSuccess, setDraftSuccess] = useState<string | null>(null);

  const [selectedIds, setSelectedIds] = useState<Set<number>>(() => new Set());
  const [bulkQuarter, setBulkQuarter] = useState('Q3 2026');
  const [bulkJob, setBulkJob] = useState<BulkEmailDraftJobStatus | null>(null);
  const [bulkRunning, setBulkRunning] = useState(false);
  const [retryIds, setRetryIds] = useState<number[] | null>(null);
  const headerCbRef = useRef<HTMLInputElement>(null);
  const pollRef = useRef<number | null>(null);

  useEffect(() => {
    const t = window.setTimeout(() => setSearch(searchInput.trim()), 300);
    return () => window.clearTimeout(t);
  }, [searchInput]);

  const query = useMemo(
    () => ({
      skip: 0,
      limit: 200,
      search: search || undefined,
    }),
    [search],
  );

  const load = useCallback(async () => {
    if (!isAdminRole(userRole)) return;
    setLoading(true);
    setError(null);
    try {
      const data = await DistributorService.list(query);
      setRows(data.data);
      setTotal(data.total);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load distributors');
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, [query, userRole]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    return () => {
      if (pollRef.current != null) {
        window.clearInterval(pollRef.current);
      }
    };
  }, []);

  const selectableRows = useMemo(() => rows.filter(d => !d.is_deleted), [rows]);
  const selectedCount = selectedIds.size;
  const allVisibleSelected =
    selectableRows.length > 0 && selectableRows.every(d => selectedIds.has(d.id));
  const someVisibleSelected = selectableRows.some(d => selectedIds.has(d.id));

  useEffect(() => {
    if (headerCbRef.current) {
      headerCbRef.current.indeterminate = someVisibleSelected && !allVisibleSelected;
    }
  }, [someVisibleSelected, allVisibleSelected]);

  if (!isAdminRole(userRole)) {
    return <Navigate to="/" replace />;
  }

  const stopPolling = () => {
    if (pollRef.current != null) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
  };

  const closeDialog = () => {
    if (busy || bulkRunning) return;
    setDialog(null);
    setTarget(null);
    setFormError(null);
    setCustomers([]);
    setReportingQuarter('');
    setRetryIds(null);
  };

  const openCreate = () => {
    setTarget(null);
    setForm(emptyForm());
    setFormError(null);
    setDialog('create');
  };

  const openEdit = (d: Distributor) => {
    setTarget(d);
    setForm(formFromDistributor(d));
    setFormError(null);
    setDialog('edit');
  };

  const openCustomers = async (d: Distributor) => {
    setTarget(d);
    setFormError(null);
    setCustomers([]);
    setDialog('customers');
    setCustomersLoading(true);
    try {
      const names = await DistributorService.listCustomers(d.id);
      setCustomers(names);
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : 'Failed to load customers');
    } finally {
      setCustomersLoading(false);
    }
  };

  const openPackage = (d: Distributor) => {
    if (bulkRunning) return;
    setTarget(d);
    setReportingQuarter('');
    setFormError(null);
    setDraftSuccess(null);
    setDialog('package');
  };

  const openDeactivate = (d: Distributor) => {
    setTarget(d);
    setFormError(null);
    setDialog('deactivate');
  };

  const toggleRow = (id: number) => {
    if (bulkRunning) return;
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleSelectAllVisible = () => {
    if (bulkRunning) return;
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (allVisibleSelected) {
        selectableRows.forEach(d => next.delete(d.id));
      } else {
        selectableRows.forEach(d => next.add(d.id));
      }
      return next;
    });
  };

  const openBulkConfirm = (ids?: number[]) => {
    if (bulkRunning) return;
    const count = ids?.length ?? selectedIds.size;
    if (count === 0) return;
    if (ids) setRetryIds(ids);
    else setRetryIds(null);
    setFormError(null);
    setBulkJob(null);
    setDialog('bulkConfirm');
  };

  const pollJob = (jobId: string) => {
    stopPolling();
    const tick = async () => {
      try {
        const status = await DistributorService.getBulkEmailDraftJob(jobId);
        setBulkJob(status);
        if (status.status === 'completed' || status.status === 'failed') {
          stopPolling();
          setBulkRunning(false);
        }
      } catch (err) {
        stopPolling();
        setBulkRunning(false);
        setFormError(err instanceof ApiError ? err.message : 'Failed to poll bulk draft job');
      }
    };
    void tick();
    pollRef.current = window.setInterval(() => void tick(), 1000);
  };

  const startBulkJob = async (ids: number[], quarter: string) => {
    if (bulkRunning || ids.length === 0) return;
    setBulkRunning(true);
    setFormError(null);
    setBulkJob(null);
    setDialog('bulkProgress');
    try {
      const started = await DistributorService.startBulkEmailDrafts(ids, quarter);
      setBulkJob({
        job_id: started.job_id,
        status: started.status,
        reporting_quarter: started.reporting_quarter,
        total: started.total,
        processed: 0,
        successful: 0,
        failed: 0,
        results: [],
      });
      pollJob(started.job_id);
    } catch (err) {
      setBulkRunning(false);
      setFormError(err instanceof ApiError ? err.message : 'Unable to start bulk draft creation');
      setDialog('bulkConfirm');
    }
  };

  const onConfirmBulk = async (e: FormEvent) => {
    e.preventDefault();
    const quarter = bulkQuarter.trim();
    if (!quarter) {
      setFormError('Reporting quarter is required (e.g. Q3 2026)');
      return;
    }
    const ids = retryIds ?? Array.from(selectedIds);
    if (ids.length === 0) return;
    await startBulkJob(ids, quarter);
  };

  const onRetryFailed = async () => {
    const failed = (bulkJob?.results || []).filter(r => !r.success).map(r => r.distributor_id);
    if (failed.length === 0 || bulkRunning) return;
    setSelectedIds(new Set(failed));
    setRetryIds(failed);
    await load();
    setFormError(null);
    setDialog('bulkConfirm');
  };

  const onSaveForm = async (e: FormEvent) => {
    e.preventDefault();
    setFormError(null);
    const payload = toPayload(form);
    if (!payload.name || !payload.company) {
      setFormError('Name and company are required');
      return;
    }
    setBusy(true);
    try {
      if (dialog === 'edit' && target) {
        await DistributorService.update(target.id, payload);
      } else {
        await DistributorService.create(payload);
      }
      closeDialog();
      await load();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : 'Save failed');
    } finally {
      setBusy(false);
    }
  };

  const onConfirmDeactivate = async () => {
    if (!target) return;
    setBusy(true);
    setFormError(null);
    try {
      await DistributorService.deactivate(target.id);
      closeDialog();
      await load();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : 'Deactivate failed');
    } finally {
      setBusy(false);
    }
  };

  const onCreateEmailDraft = async (e: FormEvent) => {
    e.preventDefault();
    if (!target || busy || bulkRunning) return;
    const quarter = reportingQuarter.trim();
    if (!quarter) {
      setFormError('Reporting quarter is required (e.g. Q2 2026)');
      return;
    }
    setBusy(true);
    setFormError(null);
    setDraftSuccess(null);
    try {
      const result = await DistributorService.createEmailDraft(target.id, quarter);
      setDraftSuccess(
        result.message ||
          `Email draft created successfully in ${result.mailbox}. Please open Outlook → Drafts to review and send.`,
      );
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : 'Unable to create the Outlook draft.');
    } finally {
      setBusy(false);
    }
  };

  const actionBtn = (danger = false): CSSProperties => ({
    display: 'inline-flex',
    alignItems: 'center',
    gap: 4,
    height: 28,
    padding: '0 8px',
    fontSize: '0.75rem',
    fontWeight: 600,
    border: `1px solid ${danger ? 'rgba(220,38,38,0.3)' : BORDER}`,
    borderRadius: 6,
    background: 'white',
    color: danger ? RED : '#374151',
    cursor: bulkRunning ? 'not-allowed' : 'pointer',
    opacity: bulkRunning ? 0.55 : 1,
    whiteSpace: 'nowrap',
    flexShrink: 0,
  });

  const cellPad: CSSProperties = {
    padding: '12px 16px',
    verticalAlign: 'middle',
  };

  const setField = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm(prev => ({ ...prev, [key]: value }));
  };

  const bulkIdsForConfirm = retryIds ?? Array.from(selectedIds);
  const bulkConfirmCount = bulkIdsForConfirm.length;
  const failedResults = (bulkJob?.results || []).filter(r => !r.success);
  const jobDone = bulkJob && (bulkJob.status === 'completed' || bulkJob.status === 'failed');

  return (
    <div
      style={{
        padding: '24px',
        maxWidth: 1280,
        margin: '0 auto',
        fontFamily: "'Inter', system-ui, sans-serif",
      }}
    >
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: '1.5rem', fontWeight: 700, color: '#111827', margin: '0 0 6px' }}>
          Distributor Management
        </h1>
        <p style={{ margin: 0, color: '#6B7280', fontSize: '0.875rem' }}>
          Manage distributor contacts, customer mappings, and quarterly Outlook packages.
        </p>
      </div>

      <StatusBanner loading={loading && rows.length === 0} error={error} onRetry={load} />

      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: 12,
          alignItems: 'center',
          marginBottom: 16,
          padding: 16,
          background: 'white',
          border: `1px solid ${BORDER}`,
          borderRadius: 10,
        }}
      >
        <div style={{ position: 'relative', flex: '1 1 220px', minWidth: 200 }}>
          <Search
            size={15}
            style={{
              position: 'absolute',
              left: 12,
              top: '50%',
              transform: 'translateY(-50%)',
              color: '#9CA3AF',
            }}
          />
          <input
            value={searchInput}
            onChange={e => setSearchInput(e.target.value)}
            placeholder="Search company, name, email…"
            style={{ ...inputStyle, paddingLeft: 36 }}
          />
        </div>

        <button
          type="button"
          onClick={() => openBulkConfirm()}
          disabled={selectedCount === 0 || bulkRunning}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6,
            padding: '9px 14px',
            fontSize: '0.8125rem',
            fontWeight: 600,
            border: 'none',
            borderRadius: 8,
            background: selectedCount === 0 || bulkRunning ? '#9CA3AF' : BLUE,
            color: 'white',
            cursor: selectedCount === 0 || bulkRunning ? 'not-allowed' : 'pointer',
          }}
          title="Create Outlook drafts for all selected distributors (not sent)"
        >
          <Mail size={15} />
          {selectedCount > 0 ? `Create Drafts (${selectedCount})` : 'Create Drafts'}
        </button>

        <button
          type="button"
          onClick={openCreate}
          disabled={bulkRunning}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6,
            padding: '9px 14px',
            fontSize: '0.8125rem',
            fontWeight: 600,
            border: 'none',
            borderRadius: 8,
            background: TEAL,
            color: 'white',
            cursor: bulkRunning ? 'not-allowed' : 'pointer',
            marginLeft: 'auto',
            opacity: bulkRunning ? 0.7 : 1,
          }}
        >
          <Plus size={15} />
          Add Distributor
        </button>
      </div>

      <div
        style={{
          background: 'white',
          border: `1px solid ${BORDER}`,
          borderRadius: 10,
          overflow: 'hidden',
        }}
      >
        <div style={{ overflowX: 'auto' }}>
          <table
            style={{
              width: '100%',
              minWidth: 1100,
              borderCollapse: 'collapse',
              fontSize: '0.875rem',
            }}
          >
            <thead>
              <tr style={{ background: '#F9FAFB', borderBottom: `1px solid ${BORDER}` }}>
                <th
                  style={{
                    width: 48,
                    minWidth: 48,
                    maxWidth: 48,
                    padding: '12px 8px',
                    textAlign: 'center',
                    verticalAlign: 'middle',
                  }}
                >
                  <input
                    ref={headerCbRef}
                    type="checkbox"
                    checked={allVisibleSelected}
                    disabled={bulkRunning || selectableRows.length === 0}
                    onChange={toggleSelectAllVisible}
                    aria-label="Select all distributors"
                  />
                </th>
                {['Distributor', 'Contact Person', 'Email', 'Active', 'Customers', 'Actions'].map(
                  h => (
                    <th
                      key={h}
                      style={{
                        textAlign: 'left',
                        padding: '12px 16px',
                        fontSize: '0.6875rem',
                        fontWeight: 700,
                        color: '#6B7280',
                        textTransform: 'uppercase',
                        letterSpacing: '0.05em',
                        verticalAlign: 'middle',
                        whiteSpace: 'nowrap',
                        ...(h === 'Actions' ? { minWidth: 420 } : null),
                      }}
                    >
                      {h}
                    </th>
                  ),
                )}
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 && !loading ? (
                <tr>
                  <td colSpan={7} style={{ padding: 40, textAlign: 'center', color: '#9CA3AF' }}>
                    No distributors found
                  </td>
                </tr>
              ) : (
                rows.map(d => (
                  <tr key={d.id} style={{ borderBottom: `1px solid ${BORDER}` }}>
                    <td
                      style={{
                        width: 48,
                        minWidth: 48,
                        maxWidth: 48,
                        padding: '12px 8px',
                        textAlign: 'center',
                        verticalAlign: 'middle',
                      }}
                    >
                      <input
                        type="checkbox"
                        checked={selectedIds.has(d.id)}
                        disabled={bulkRunning}
                        onChange={() => toggleRow(d.id)}
                        aria-label={`Select ${d.company}`}
                      />
                    </td>
                    <td style={cellPad}>
                      <div style={{ fontWeight: 600, color: '#111827' }}>{d.company}</div>
                      {d.name && d.name !== d.company && (
                        <div style={{ fontSize: '0.75rem', color: '#6B7280', marginTop: 2 }}>
                          {d.name}
                          {d.code ? ` · ${d.code}` : ''}
                        </div>
                      )}
                    </td>
                    <td style={{ ...cellPad, color: '#374151' }}>
                      {d.contact_person || '—'}
                    </td>
                    <td style={{ ...cellPad, color: '#374151' }}>{d.email || '—'}</td>
                    <td style={cellPad}>
                      <StatusBadge active={d.is_active} />
                    </td>
                    <td style={{ ...cellPad, color: '#374151', fontWeight: 600 }}>
                      {d.customer_count ?? 0}
                    </td>
                    <td style={{ ...cellPad, minWidth: 420 }}>
                      <div
                        style={{
                          display: 'flex',
                          flexDirection: 'row',
                          flexWrap: 'nowrap',
                          alignItems: 'center',
                          gap: 8,
                          whiteSpace: 'nowrap',
                        }}
                      >
                        <button
                          type="button"
                          style={actionBtn()}
                          disabled={bulkRunning}
                          onClick={() => openEdit(d)}
                        >
                          <Pencil size={12} /> Edit
                        </button>
                        <button
                          type="button"
                          style={actionBtn()}
                          disabled={bulkRunning}
                          onClick={() => openCustomers(d)}
                        >
                          <Users size={12} /> View Customers
                        </button>
                        {d.is_active && (
                          <button
                            type="button"
                            style={actionBtn(true)}
                            disabled={bulkRunning}
                            onClick={() => openDeactivate(d)}
                          >
                            <UserX size={12} /> Deactivate
                          </button>
                        )}
                        <button
                          type="button"
                          style={actionBtn()}
                          disabled={bulkRunning}
                          onClick={() => openPackage(d)}
                          title="Create a ready-to-review Outlook draft with the distributor-specific Excel template attached."
                        >
                          <Mail size={12} /> Create Email Draft
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        <div
          style={{
            padding: '10px 16px',
            borderTop: `1px solid ${BORDER}`,
            fontSize: '0.75rem',
            color: '#6B7280',
          }}
        >
          {total} distributor{total === 1 ? '' : 's'}
          {selectedCount > 0 ? ` · ${selectedCount} selected` : ''}
        </div>
      </div>

      {dialog && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(15,23,42,0.45)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
            padding: 16,
          }}
          onClick={() => {
            if (!bulkRunning) closeDialog();
          }}
        >
          <div
            style={{
              background: 'white',
              borderRadius: 12,
              width: '100%',
              maxWidth:
                dialog === 'customers' || dialog === 'bulkProgress' || dialog === 'bulkConfirm'
                  ? 520
                  : 440,
              padding: 24,
              boxShadow: '0 20px 40px rgba(0,0,0,0.15)',
              maxHeight: '90vh',
              overflowY: 'auto',
            }}
            onClick={e => e.stopPropagation()}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: 16,
              }}
            >
              <h2 style={{ margin: 0, fontSize: '1.125rem', fontWeight: 700, color: '#111827' }}>
                {dialog === 'create' && 'Add Distributor'}
                {dialog === 'edit' && 'Edit Distributor'}
                {dialog === 'customers' && 'Customers'}
                {dialog === 'package' && 'Create Email Draft'}
                {dialog === 'deactivate' && 'Deactivate Distributor'}
                {dialog === 'bulkConfirm' && 'Create Email Drafts'}
                {dialog === 'bulkProgress' &&
                  (jobDone ? 'Bulk Draft Creation Complete' : 'Creating drafts…')}
              </h2>
              {!(bulkRunning && dialog === 'bulkProgress') && (
                <button
                  type="button"
                  onClick={closeDialog}
                  style={{
                    border: 'none',
                    background: 'transparent',
                    cursor: 'pointer',
                    color: '#6B7280',
                  }}
                >
                  <X size={18} />
                </button>
              )}
            </div>

            {formError && (
              <div
                style={{
                  padding: '10px 12px',
                  background: 'rgba(217,58,47,0.08)',
                  borderRadius: 8,
                  marginBottom: 14,
                  color: RED,
                  fontSize: '0.8125rem',
                }}
              >
                {formError}
              </div>
            )}

            {(dialog === 'create' || dialog === 'edit') && (
              <form onSubmit={onSaveForm}>
                <label style={labelStyle}>Name</label>
                <input
                  required
                  value={form.name}
                  onChange={e => setField('name', e.target.value)}
                  style={{ ...inputStyle, marginBottom: 12 }}
                />
                <label style={labelStyle}>Company</label>
                <input
                  required
                  value={form.company}
                  onChange={e => setField('company', e.target.value)}
                  style={{ ...inputStyle, marginBottom: 12 }}
                />
                <label style={labelStyle}>Code</label>
                <input
                  value={form.code}
                  onChange={e => setField('code', e.target.value)}
                  style={{ ...inputStyle, marginBottom: 12 }}
                />
                <label style={labelStyle}>Contact Person</label>
                <input
                  value={form.contact_person}
                  onChange={e => setField('contact_person', e.target.value)}
                  style={{ ...inputStyle, marginBottom: 12 }}
                />
                <label style={labelStyle}>Email</label>
                <input
                  type="email"
                  value={form.email}
                  onChange={e => setField('email', e.target.value)}
                  style={{ ...inputStyle, marginBottom: 12 }}
                />
                <label style={labelStyle}>CC Email</label>
                <input
                  type="email"
                  value={form.cc_email}
                  onChange={e => setField('cc_email', e.target.value)}
                  style={{ ...inputStyle, marginBottom: 12 }}
                />
                <label style={labelStyle}>Status</label>
                <select
                  value={form.is_active ? 'active' : 'inactive'}
                  onChange={e => setField('is_active', e.target.value === 'active')}
                  style={{ ...inputStyle, marginBottom: 20 }}
                >
                  <option value="active">Active</option>
                  <option value="inactive">Inactive</option>
                </select>
                <DialogActions
                  busy={busy}
                  onCancel={closeDialog}
                  submitLabel={dialog === 'create' ? 'Create' : 'Save'}
                />
              </form>
            )}

            {dialog === 'customers' && (
              <div>
                <p style={{ margin: '0 0 12px', fontSize: '0.8125rem', color: '#6B7280' }}>
                  Mapped customers for <strong>{target?.company}</strong>
                </p>
                {customersLoading ? (
                  <p style={{ margin: 0, color: '#9CA3AF', fontSize: '0.875rem' }}>Loading…</p>
                ) : customers.length === 0 ? (
                  <p style={{ margin: 0, color: '#9CA3AF', fontSize: '0.875rem' }}>
                    No customers mapped yet
                  </p>
                ) : (
                  <ul
                    style={{
                      margin: 0,
                      padding: '0 0 0 18px',
                      maxHeight: 320,
                      overflowY: 'auto',
                      fontSize: '0.875rem',
                      color: '#374151',
                      lineHeight: 1.7,
                    }}
                  >
                    {customers.map(name => (
                      <li key={name}>{name}</li>
                    ))}
                  </ul>
                )}
                <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 20 }}>
                  <button type="button" onClick={closeDialog} style={secondaryBtn}>
                    Close
                  </button>
                </div>
              </div>
            )}

            {dialog === 'package' && (
              <form onSubmit={onCreateEmailDraft}>
                <p style={{ margin: '0 0 12px', fontSize: '0.8125rem', color: '#6B7280' }}>
                  Create an Outlook draft in the APCOTEX mailbox with the distributor-specific
                  Excel template attached for <strong>{target?.company}</strong>. The email is{' '}
                  <strong>not</strong> sent automatically — open Outlook → Drafts to review and
                  Send.
                </p>
                <label style={labelStyle}>Reporting Quarter</label>
                <input
                  required
                  value={reportingQuarter}
                  onChange={e => setReportingQuarter(e.target.value)}
                  placeholder="e.g. Q3 2026"
                  disabled={busy}
                  style={{ ...inputStyle, marginBottom: 12 }}
                />
                {draftSuccess && (
                  <p
                    style={{
                      margin: '0 0 12px',
                      padding: '10px 12px',
                      fontSize: '0.8125rem',
                      color: '#065F46',
                      background: 'rgba(16,185,129,0.08)',
                      border: '1px solid rgba(16,185,129,0.25)',
                      borderRadius: 8,
                      lineHeight: 1.45,
                    }}
                  >
                    {draftSuccess}
                  </p>
                )}
                <DialogActions
                  busy={busy}
                  onCancel={closeDialog}
                  submitLabel={busy ? 'Creating email draft…' : 'Create Email Draft'}
                  hideSubmit={Boolean(draftSuccess)}
                />
              </form>
            )}

            {dialog === 'bulkConfirm' && (
              <form onSubmit={onConfirmBulk}>
                <p
                  style={{
                    margin: '0 0 12px',
                    fontSize: '0.875rem',
                    color: '#374151',
                    lineHeight: 1.55,
                  }}
                >
                  You are about to create <strong>{bulkConfirmCount}</strong> Outlook draft
                  {bulkConfirmCount === 1 ? '' : 's'}.
                </p>
                <p style={{ margin: '0 0 12px', fontSize: '0.8125rem', color: '#6B7280', lineHeight: 1.5 }}>
                  Each distributor will receive a separate draft containing their
                  distributor-specific Excel template.
                </p>
                <p style={{ margin: '0 0 12px', fontSize: '0.8125rem', color: '#6B7280', lineHeight: 1.5 }}>
                  No emails will be sent automatically.
                </p>
                <p style={{ margin: '0 0 16px', fontSize: '0.8125rem', color: '#6B7280', lineHeight: 1.5 }}>
                  The drafts will be created in: <strong>salesinsights@apcotex.com</strong>
                </p>
                <label style={labelStyle}>Reporting Quarter</label>
                <select
                  required
                  value={bulkQuarter}
                  onChange={e => setBulkQuarter(e.target.value)}
                  style={{ ...inputStyle, marginBottom: 20 }}
                >
                  {QUARTER_OPTIONS.map(q => (
                    <option key={q} value={q}>
                      {q}
                    </option>
                  ))}
                </select>
                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
                  <button type="button" onClick={closeDialog} style={secondaryBtn}>
                    Cancel
                  </button>
                  <button type="submit" style={primaryBtn}>
                    Create {bulkConfirmCount} Draft{bulkConfirmCount === 1 ? '' : 's'}
                  </button>
                </div>
              </form>
            )}

            {dialog === 'bulkProgress' && bulkJob && (
              <div>
                {!jobDone && (
                  <>
                    <p style={{ margin: '0 0 10px', fontSize: '0.9375rem', color: '#111827', fontWeight: 600 }}>
                      Creating drafts… {bulkJob.processed} / {bulkJob.total}
                    </p>
                    <p style={{ margin: '0 0 4px', fontSize: '0.8125rem', color: '#059669' }}>
                      Successful: {bulkJob.successful}
                    </p>
                    <p style={{ margin: '0 0 16px', fontSize: '0.8125rem', color: RED }}>
                      Failed: {bulkJob.failed}
                    </p>
                    <div
                      style={{
                        height: 8,
                        borderRadius: 999,
                        background: '#E5E7EB',
                        overflow: 'hidden',
                        marginBottom: 8,
                      }}
                    >
                      <div
                        style={{
                          height: '100%',
                          width: `${bulkJob.total ? (100 * bulkJob.processed) / bulkJob.total : 0}%`,
                          background: BLUE,
                          transition: 'width 0.3s ease',
                        }}
                      />
                    </div>
                  </>
                )}

                {jobDone && (
                  <>
                    <p style={{ margin: '0 0 8px', fontSize: '0.8125rem', color: '#6B7280' }}>
                      Reporting Quarter: <strong>{bulkJob.reporting_quarter}</strong>
                    </p>
                    <p style={{ margin: '0 0 4px', fontSize: '0.8125rem', color: '#6B7280' }}>
                      Total: {bulkJob.total}
                    </p>
                    {bulkJob.failed === 0 ? (
                      <p
                        style={{
                          margin: '12px 0',
                          padding: '12px',
                          borderRadius: 8,
                          background: 'rgba(16,185,129,0.08)',
                          color: '#065F46',
                          fontSize: '0.875rem',
                          lineHeight: 1.5,
                        }}
                      >
                        ✅ {bulkJob.successful} / {bulkJob.total} Outlook drafts created
                        successfully.
                        <br />
                        All drafts are available in salesinsights@apcotex.com → Drafts.
                        <br />
                        No emails were sent automatically.
                      </p>
                    ) : (
                      <>
                        <p style={{ margin: '8px 0 4px', fontSize: '0.875rem', color: '#065F46' }}>
                          ✅ Drafts Created: {bulkJob.successful}
                        </p>
                        <p style={{ margin: '0 0 12px', fontSize: '0.875rem', color: '#B45309' }}>
                          ⚠️ Failed: {bulkJob.failed}
                        </p>
                        {failedResults.length > 0 && (
                          <div style={{ marginBottom: 16 }}>
                            <div
                              style={{
                                fontSize: '0.75rem',
                                fontWeight: 700,
                                color: '#6B7280',
                                textTransform: 'uppercase',
                                marginBottom: 8,
                              }}
                            >
                              Failed Distributors
                            </div>
                            <ol
                              style={{
                                margin: 0,
                                padding: '0 0 0 18px',
                                fontSize: '0.8125rem',
                                color: '#374151',
                                lineHeight: 1.55,
                              }}
                            >
                              {failedResults.map(r => (
                                <li key={r.distributor_id} style={{ marginBottom: 8 }}>
                                  <strong>{r.distributor_name}</strong>
                                  <div style={{ color: RED }}>{r.reason || 'Unable to create Outlook draft.'}</div>
                                </li>
                              ))}
                            </ol>
                          </div>
                        )}
                      </>
                    )}
                    <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
                      {failedResults.length > 0 && (
                        <button type="button" onClick={() => void onRetryFailed()} style={primaryBtn}>
                          Retry Failed
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={() => {
                          setDialog(null);
                          setRetryIds(null);
                        }}
                        style={secondaryBtn}
                      >
                        Close
                      </button>
                    </div>
                  </>
                )}
              </div>
            )}

            {dialog === 'deactivate' && (
              <div>
                <p
                  style={{
                    margin: '0 0 20px',
                    fontSize: '0.875rem',
                    color: '#374151',
                    lineHeight: 1.5,
                  }}
                >
                  Deactivate <strong>{target?.company}</strong>? The distributor will be marked
                  inactive and excluded from active lists.
                </p>
                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
                  <button type="button" onClick={closeDialog} disabled={busy} style={secondaryBtn}>
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={onConfirmDeactivate}
                    disabled={busy}
                    style={{ ...primaryBtn, background: RED }}
                  >
                    {busy ? 'Deactivating…' : 'Deactivate'}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function DialogActions({
  busy,
  onCancel,
  submitLabel,
  hideSubmit = false,
}: {
  busy: boolean;
  onCancel: () => void;
  submitLabel: string;
  hideSubmit?: boolean;
}) {
  return (
    <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
      <button type="button" onClick={onCancel} disabled={busy} style={secondaryBtn}>
        {hideSubmit ? 'Close' : 'Cancel'}
      </button>
      {!hideSubmit && (
        <button type="submit" disabled={busy} style={{ ...primaryBtn, opacity: busy ? 0.7 : 1 }}>
          {submitLabel}
        </button>
      )}
    </div>
  );
}
