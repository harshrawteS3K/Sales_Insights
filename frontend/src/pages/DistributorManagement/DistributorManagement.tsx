import { useCallback, useEffect, useMemo, useState, type CSSProperties, type FormEvent } from 'react';
import {
  Search,
  Plus,
  Pencil,
  Users,
  UserX,
  Package,
  X,
} from 'lucide-react';
import { Navigate } from 'react-router';
import { useLayoutContext } from '../../hooks/useLayoutContext';
import { StatusBanner } from '../../components/common/StatusBanner';
import { DistributorService } from '../../services/distributor.service';
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

type DialogMode = 'create' | 'edit' | 'customers' | 'package' | 'deactivate' | null;

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

  if (!isAdminRole(userRole)) {
    return <Navigate to="/" replace />;
  }

  const closeDialog = () => {
    if (busy) return;
    setDialog(null);
    setTarget(null);
    setFormError(null);
    setCustomers([]);
    setReportingQuarter('');
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
    setTarget(d);
    setReportingQuarter('');
    setFormError(null);
    setDialog('package');
  };

  const openDeactivate = (d: Distributor) => {
    setTarget(d);
    setFormError(null);
    setDialog('deactivate');
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

  const onGeneratePackage = async (e: FormEvent) => {
    e.preventDefault();
    if (!target) return;
    const quarter = reportingQuarter.trim();
    if (!quarter) {
      setFormError('Reporting quarter is required (e.g. Q2 2026)');
      return;
    }
    setBusy(true);
    setFormError(null);
    try {
      await DistributorService.generateQuarterlyPackage(target.id, quarter);
      closeDialog();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : 'Package generation failed');
    } finally {
      setBusy(false);
    }
  };

  const actionBtn = (danger = false): CSSProperties => ({
    display: 'inline-flex',
    alignItems: 'center',
    gap: 4,
    padding: '5px 8px',
    fontSize: '0.75rem',
    fontWeight: 600,
    border: `1px solid ${danger ? 'rgba(220,38,38,0.3)' : BORDER}`,
    borderRadius: 6,
    background: 'white',
    color: danger ? RED : '#374151',
    cursor: 'pointer',
  });

  const setField = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm(prev => ({ ...prev, [key]: value }));
  };

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
          onClick={openCreate}
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
            cursor: 'pointer',
            marginLeft: 'auto',
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
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
            <thead>
              <tr style={{ background: '#F9FAFB', borderBottom: `1px solid ${BORDER}` }}>
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
                  <td colSpan={6} style={{ padding: 40, textAlign: 'center', color: '#9CA3AF' }}>
                    No distributors found
                  </td>
                </tr>
              ) : (
                rows.map(d => (
                  <tr key={d.id} style={{ borderBottom: `1px solid ${BORDER}` }}>
                    <td style={{ padding: '14px 16px' }}>
                      <div style={{ fontWeight: 600, color: '#111827' }}>{d.company}</div>
                      {d.name && d.name !== d.company && (
                        <div style={{ fontSize: '0.75rem', color: '#6B7280', marginTop: 2 }}>
                          {d.name}
                          {d.code ? ` · ${d.code}` : ''}
                        </div>
                      )}
                    </td>
                    <td style={{ padding: '14px 16px', color: '#374151' }}>
                      {d.contact_person || '—'}
                    </td>
                    <td style={{ padding: '14px 16px', color: '#374151' }}>{d.email || '—'}</td>
                    <td style={{ padding: '14px 16px' }}>
                      <StatusBadge active={d.is_active} />
                    </td>
                    <td style={{ padding: '14px 16px', color: '#374151', fontWeight: 600 }}>
                      {d.customer_count ?? 0}
                    </td>
                    <td style={{ padding: '14px 16px' }}>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                        <button type="button" style={actionBtn()} onClick={() => openEdit(d)}>
                          <Pencil size={12} /> Edit
                        </button>
                        <button type="button" style={actionBtn()} onClick={() => openCustomers(d)}>
                          <Users size={12} /> View Customers
                        </button>
                        {d.is_active && (
                          <button
                            type="button"
                            style={actionBtn(true)}
                            onClick={() => openDeactivate(d)}
                          >
                            <UserX size={12} /> Deactivate
                          </button>
                        )}
                        <button type="button" style={actionBtn()} onClick={() => openPackage(d)}>
                          <Package size={12} /> Generate Package
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
          onClick={closeDialog}
        >
          <div
            style={{
              background: 'white',
              borderRadius: 12,
              width: '100%',
              maxWidth: dialog === 'customers' ? 480 : 440,
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
                {dialog === 'package' && 'Generate Quarterly Package'}
                {dialog === 'deactivate' && 'Deactivate Distributor'}
              </h2>
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
              <form onSubmit={onGeneratePackage}>
                <p style={{ margin: '0 0 12px', fontSize: '0.8125rem', color: '#6B7280' }}>
                  Generate Outlook-ready ZIP (template + draft) for{' '}
                  <strong>{target?.company}</strong>.
                </p>
                <label style={labelStyle}>Reporting Quarter</label>
                <input
                  required
                  value={reportingQuarter}
                  onChange={e => setReportingQuarter(e.target.value)}
                  placeholder="e.g. Q2 2026"
                  style={{ ...inputStyle, marginBottom: 20 }}
                />
                <DialogActions busy={busy} onCancel={closeDialog} submitLabel="Download ZIP" />
              </form>
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
}: {
  busy: boolean;
  onCancel: () => void;
  submitLabel: string;
}) {
  return (
    <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
      <button type="button" onClick={onCancel} disabled={busy} style={secondaryBtn}>
        Cancel
      </button>
      <button type="submit" disabled={busy} style={primaryBtn}>
        {busy ? 'Saving…' : submitLabel}
      </button>
    </div>
  );
}
