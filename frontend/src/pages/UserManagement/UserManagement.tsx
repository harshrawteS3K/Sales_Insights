import { useCallback, useEffect, useMemo, useState, type CSSProperties, type FormEvent } from 'react';
import {
  Search,
  Download,
  Plus,
  Pencil,
  KeyRound,
  UserX,
  UserCheck,
  Trash2,
  X,
  Filter,
} from 'lucide-react';
import { Navigate } from 'react-router';
import { useLayoutContext } from '../../hooks/useLayoutContext';
import { StatusBanner } from '../../components/common/StatusBanner';
import { UserManagementService } from '../../services/userManagement.service';
import { ApiError } from '../../api';
import { BLUE, BORDER, RED, TEAL } from '../../constants/theme';
import { isSuperAdminRole } from '../../utils/rbac';
import type { ManagedUser } from '../../types';

const inputStyle: CSSProperties = {
  width: '100%',
  padding: '9px 12px',
  fontSize: '0.875rem',
  border: `1px solid ${BORDER}`,
  borderRadius: 8,
  outline: 'none',
};

function RoleBadge({ role }: { role: string }) {
  const map: Record<string, { color: string; bg: string; label: string }> = {
    super_admin: { color: '#7C3AED', bg: 'rgba(124,58,237,0.12)', label: 'Super Admin' },
    admin: { color: '#1F5FA8', bg: 'rgba(31,95,168,0.12)', label: 'Admin' },
    user: { color: '#0F766E', bg: 'rgba(15,118,110,0.12)', label: 'User' },
  };
  const style = map[role] || { color: '#6B7280', bg: 'rgba(107,114,128,0.1)', label: role };
  return (
    <span
      style={{
        display: 'inline-flex',
        padding: '3px 10px',
        borderRadius: 999,
        fontSize: '0.6875rem',
        fontWeight: 700,
        color: style.color,
        background: style.bg,
        letterSpacing: '0.03em',
      }}
    >
      {style.label}
    </span>
  );
}

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

type DialogMode = 'create' | 'username' | 'password' | 'delete' | null;

export function UserManagement() {
  const { userRole } = useLayoutContext();
  const [rows, setRows] = useState<ManagedUser[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchInput, setSearchInput] = useState('');
  const [search, setSearch] = useState('');
  const [roleFilter, setRoleFilter] = useState('All');
  const [statusFilter, setStatusFilter] = useState('All');
  const [exporting, setExporting] = useState(false);

  const [dialog, setDialog] = useState<DialogMode>(null);
  const [target, setTarget] = useState<ManagedUser | null>(null);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  // Create form
  const [fullName, setFullName] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [createRole, setCreateRole] = useState<'admin' | 'user'>('user');
  const [createActive, setCreateActive] = useState(true);

  useEffect(() => {
    const t = window.setTimeout(() => setSearch(searchInput.trim()), 300);
    return () => window.clearTimeout(t);
  }, [searchInput]);

  const query = useMemo(
    () => ({
      skip: 0,
      limit: 200,
      search: search || undefined,
      role: roleFilter !== 'All' ? roleFilter : undefined,
      status: statusFilter !== 'All' ? statusFilter : undefined,
    }),
    [search, roleFilter, statusFilter]
  );

  const load = useCallback(async () => {
    if (!isSuperAdminRole(userRole)) return;
    setLoading(true);
    setError(null);
    try {
      const data = await UserManagementService.list(query);
      setRows(data.data);
      setTotal(data.total);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load users');
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, [query, userRole]);

  useEffect(() => {
    load();
  }, [load]);

  if (!isSuperAdminRole(userRole)) {
    return <Navigate to="/" replace />;
  }

  const openCreate = () => {
    setTarget(null);
    setFullName('');
    setUsername('');
    setPassword('');
    setConfirmPassword('');
    setCreateRole('user');
    setCreateActive(true);
    setFormError(null);
    setDialog('create');
  };

  const openUsername = (user: ManagedUser) => {
    setTarget(user);
    setUsername(user.username);
    setFormError(null);
    setDialog('username');
  };

  const openPassword = (user: ManagedUser) => {
    setTarget(user);
    setPassword('');
    setConfirmPassword('');
    setFormError(null);
    setDialog('password');
  };

  const openDelete = (user: ManagedUser) => {
    setTarget(user);
    setFormError(null);
    setDialog('delete');
  };

  const closeDialog = () => {
    if (busy) return;
    setDialog(null);
    setTarget(null);
    setFormError(null);
  };

  const onCreate = async (e: FormEvent) => {
    e.preventDefault();
    setFormError(null);
    if (password !== confirmPassword) {
      setFormError('Passwords do not match');
      return;
    }
    setBusy(true);
    try {
      await UserManagementService.create({
        full_name: fullName.trim(),
        username: username.trim(),
        password,
        role: createRole,
        is_active: createActive,
      });
      closeDialog();
      await load();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : 'Create failed');
    } finally {
      setBusy(false);
    }
  };

  const onSaveUsername = async (e: FormEvent) => {
    e.preventDefault();
    if (!target) return;
    setBusy(true);
    setFormError(null);
    try {
      await UserManagementService.updateUsername(target.id, username.trim());
      closeDialog();
      await load();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : 'Update failed');
    } finally {
      setBusy(false);
    }
  };

  const onSavePassword = async (e: FormEvent) => {
    e.preventDefault();
    if (!target) return;
    setFormError(null);
    if (password !== confirmPassword) {
      setFormError('Passwords do not match');
      return;
    }
    setBusy(true);
    try {
      await UserManagementService.changePassword(target.id, password, confirmPassword);
      closeDialog();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : 'Password change failed');
    } finally {
      setBusy(false);
    }
  };

  const onToggleStatus = async (user: ManagedUser) => {
    setError(null);
    try {
      await UserManagementService.setStatus(user.id, !user.is_active);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Status update failed');
    }
  };

  const onConfirmDelete = async () => {
    if (!target) return;
    setBusy(true);
    setFormError(null);
    try {
      await UserManagementService.remove(target.id);
      closeDialog();
      await load();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : 'Delete failed');
    } finally {
      setBusy(false);
    }
  };

  const onExport = async () => {
    setExporting(true);
    try {
      await UserManagementService.exportExcel(query);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Export failed');
    } finally {
      setExporting(false);
    }
  };

  const actionBtn = (label: string, onClick: () => void, danger = false): CSSProperties => ({
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

  return (
    <div style={{ padding: '24px', maxWidth: 1280, margin: '0 auto' }}>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: '1.5rem', fontWeight: 700, color: '#111827', margin: '0 0 6px' }}>
          User Management
        </h1>
        <p style={{ margin: 0, color: '#6B7280', fontSize: '0.875rem' }}>
          Identity administration for Admin and User accounts — Super Admin only.
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
            style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: '#9CA3AF' }}
          />
          <input
            value={searchInput}
            onChange={e => setSearchInput(e.target.value)}
            placeholder="Search username, name, email…"
            style={{ ...inputStyle, paddingLeft: 36 }}
          />
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Filter size={14} color="#9CA3AF" />
          <select
            value={roleFilter}
            onChange={e => setRoleFilter(e.target.value)}
            style={{ ...inputStyle, width: 'auto', minWidth: 120 }}
          >
            <option value="All">All Roles</option>
            <option value="admin">Admin</option>
            <option value="user">User</option>
          </select>
          <select
            value={statusFilter}
            onChange={e => setStatusFilter(e.target.value)}
            style={{ ...inputStyle, width: 'auto', minWidth: 120 }}
          >
            <option value="All">All Status</option>
            <option value="Active">Active</option>
            <option value="Inactive">Inactive</option>
          </select>
        </div>

        <div style={{ display: 'flex', gap: 8, marginLeft: 'auto' }}>
          <button
            type="button"
            onClick={onExport}
            disabled={exporting}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              padding: '9px 14px',
              fontSize: '0.8125rem',
              fontWeight: 600,
              border: `1px solid ${BORDER}`,
              borderRadius: 8,
              background: 'white',
              color: '#374151',
              cursor: exporting ? 'wait' : 'pointer',
            }}
          >
            <Download size={15} />
            {exporting ? 'Exporting…' : 'Export'}
          </button>
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
            }}
          >
            <Plus size={15} />
            Create User
          </button>
        </div>
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
                {['Username', 'Full Name', 'Role', 'Status', 'Actions'].map(h => (
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
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 && !loading ? (
                <tr>
                  <td colSpan={5} style={{ padding: 40, textAlign: 'center', color: '#9CA3AF' }}>
                    No users found
                  </td>
                </tr>
              ) : (
                rows.map(user => (
                  <tr key={user.id} style={{ borderBottom: `1px solid ${BORDER}` }}>
                    <td style={{ padding: '14px 16px', fontWeight: 600, color: '#111827' }}>
                      {user.username}
                    </td>
                    <td style={{ padding: '14px 16px', color: '#374151' }}>{user.full_name}</td>
                    <td style={{ padding: '14px 16px' }}>
                      <RoleBadge role={user.role} />
                    </td>
                    <td style={{ padding: '14px 16px' }}>
                      <StatusBadge active={user.is_active} />
                    </td>
                    <td style={{ padding: '14px 16px' }}>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                        <button type="button" style={actionBtn('edit', () => {})} onClick={() => openUsername(user)}>
                          <Pencil size={12} /> Edit Username
                        </button>
                        <button type="button" style={actionBtn('pw', () => {})} onClick={() => openPassword(user)}>
                          <KeyRound size={12} /> Change Password
                        </button>
                        <button type="button" style={actionBtn('st', () => {})} onClick={() => onToggleStatus(user)}>
                          {user.is_active ? <UserX size={12} /> : <UserCheck size={12} />}
                          {user.is_active ? 'Disable' : 'Enable'}
                        </button>
                        <button
                          type="button"
                          style={actionBtn('del', () => {}, true)}
                          onClick={() => openDelete(user)}
                        >
                          <Trash2 size={12} /> Delete
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
          {total} user{total === 1 ? '' : 's'}
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
              maxWidth: 440,
              padding: 24,
              boxShadow: '0 20px 40px rgba(0,0,0,0.15)',
            }}
            onClick={e => e.stopPropagation()}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
              <h2 style={{ margin: 0, fontSize: '1.125rem', fontWeight: 700, color: '#111827' }}>
                {dialog === 'create' && 'Create User'}
                {dialog === 'username' && 'Edit Username'}
                {dialog === 'password' && 'Change Password'}
                {dialog === 'delete' && 'Delete User'}
              </h2>
              <button
                type="button"
                onClick={closeDialog}
                style={{ border: 'none', background: 'transparent', cursor: 'pointer', color: '#6B7280' }}
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

            {dialog === 'create' && (
              <form onSubmit={onCreate}>
                <label style={labelStyle}>Full Name</label>
                <input required value={fullName} onChange={e => setFullName(e.target.value)} style={{ ...inputStyle, marginBottom: 12 }} />
                <label style={labelStyle}>Username</label>
                <input required value={username} onChange={e => setUsername(e.target.value)} style={{ ...inputStyle, marginBottom: 12 }} />
                <label style={labelStyle}>Password</label>
                <input required type="password" value={password} onChange={e => setPassword(e.target.value)} style={{ ...inputStyle, marginBottom: 12 }} />
                <label style={labelStyle}>Confirm Password</label>
                <input required type="password" value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)} style={{ ...inputStyle, marginBottom: 12 }} />
                <label style={labelStyle}>Role</label>
                <select value={createRole} onChange={e => setCreateRole(e.target.value as 'admin' | 'user')} style={{ ...inputStyle, marginBottom: 12 }}>
                  <option value="user">User</option>
                  <option value="admin">Admin</option>
                </select>
                <label style={labelStyle}>Status</label>
                <select
                  value={createActive ? 'active' : 'inactive'}
                  onChange={e => setCreateActive(e.target.value === 'active')}
                  style={{ ...inputStyle, marginBottom: 20 }}
                >
                  <option value="active">Active</option>
                  <option value="inactive">Inactive</option>
                </select>
                <DialogActions busy={busy} onCancel={closeDialog} submitLabel="Create" />
              </form>
            )}

            {dialog === 'username' && (
              <form onSubmit={onSaveUsername}>
                <p style={{ margin: '0 0 12px', fontSize: '0.8125rem', color: '#6B7280' }}>
                  Updating username for <strong>{target?.full_name}</strong>
                </p>
                <label style={labelStyle}>Username</label>
                <input required value={username} onChange={e => setUsername(e.target.value)} style={{ ...inputStyle, marginBottom: 20 }} />
                <DialogActions busy={busy} onCancel={closeDialog} submitLabel="Save" />
              </form>
            )}

            {dialog === 'password' && (
              <form onSubmit={onSavePassword}>
                <p style={{ margin: '0 0 12px', fontSize: '0.8125rem', color: '#6B7280' }}>
                  Assign a new password for <strong>{target?.full_name}</strong>. Current password is never shown.
                </p>
                <label style={labelStyle}>New Password</label>
                <input required type="password" value={password} onChange={e => setPassword(e.target.value)} style={{ ...inputStyle, marginBottom: 12 }} />
                <label style={labelStyle}>Confirm Password</label>
                <input required type="password" value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)} style={{ ...inputStyle, marginBottom: 20 }} />
                <DialogActions busy={busy} onCancel={closeDialog} submitLabel="Update Password" />
              </form>
            )}

            {dialog === 'delete' && (
              <div>
                <p style={{ margin: '0 0 20px', fontSize: '0.875rem', color: '#374151', lineHeight: 1.5 }}>
                  Permanently remove <strong>{target?.full_name}</strong> ({target?.username})?
                  This cannot be undone. Super Admin cannot be deleted.
                </p>
                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
                  <button type="button" onClick={closeDialog} disabled={busy} style={secondaryBtn}>
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={onConfirmDelete}
                    disabled={busy}
                    style={{ ...primaryBtn, background: RED }}
                  >
                    {busy ? 'Deleting…' : 'Delete'}
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
