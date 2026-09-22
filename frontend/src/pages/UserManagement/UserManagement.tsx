import { Fragment, useCallback, useEffect, useMemo, useState, type CSSProperties, type FormEvent } from 'react';
import {
  Search,
  Download,
  Plus,
  KeyRound,
  UserX,
  UserCheck,
  X,
  Grid,
  List,
  ShieldCheck,
  Upload,
  FileSpreadsheet,
  ChevronDown,
  ChevronRight,
  Building2,
  CheckCircle2,
  AlertCircle,
  Trash2,
  Pencil,
} from 'lucide-react';
import { Navigate } from 'react-router';
import { useLayoutContext } from '../../hooks/useLayoutContext';
import { StatusBanner } from '../../components/common/StatusBanner';
import { UserManagementService } from '../../services/userManagement.service';
import { DistributorService } from '../../services/distributor.service';
import { ApiError } from '../../api';
import { BLUE, BORDER, RED, TEAL } from '../../constants/theme';
import { isAdminRole, isSuperAdminRole } from '../../utils/rbac';
import type { ManagedUser } from '../../types';

const inputStyle: CSSProperties = {
  width: '100%',
  padding: '9px 12px',
  fontSize: '0.875rem',
  border: `1px solid ${BORDER}`,
  borderRadius: 8,
  outline: 'none',
};

const ALL_SEGMENTS = ['Paper', 'Carpet', 'Construction', 'Rubber', 'Gloves'];

function RoleBadge({ role }: { role: string }) {
  const map: Record<string, { color: string; bg: string; label: string }> = {
    super_admin: { color: '#7C3AED', bg: 'rgba(124,58,237,0.12)', label: 'Super Admin' },
    admin: { color: '#1F5FA8', bg: 'rgba(31,95,168,0.12)', label: 'Admin' },
    user: { color: '#0F766E', bg: 'rgba(15,118,110,0.12)', label: 'Sales Owner' },
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

type DialogMode = 'create' | 'password' | 'segments' | 'username' | 'email' | 'distributors' | 'renameDistributors' | null;
type ActiveTab = 'matrix' | 'users';

export function UserManagement() {
  const { userRole } = useLayoutContext();
  const [activeTab, setActiveTab] = useState<ActiveTab>('matrix');
  const [rows, setRows] = useState<ManagedUser[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [searchInput, setSearchInput] = useState('');
  const [search, setSearch] = useState('');
  const [roleFilter, setRoleFilter] = useState('All');
  const [statusFilter, setStatusFilter] = useState('All');
  const [exporting, setExporting] = useState(false);

  // Expandable Row State for Matrix Table
  const [expandedUserIds, setExpandedUserIds] = useState<number[]>([]);

  // Matrix State
  const [matrixData, setMatrixData] = useState<{ segments: string[]; rows: any[] }>({
    segments: ALL_SEGMENTS,
    rows: [],
  });
  const [matrixLoading, setMatrixLoading] = useState(false);
  const [matrixSaving, setMatrixSaving] = useState<Record<string, boolean>>({});
  const [untickConfirm, setUntickConfirm] = useState<{
    userId: number;
    userName: string;
    segment: string;
  } | null>(null);
  const [retainHistoryChoice, setRetainHistoryChoice] = useState<'yes' | 'no'>('yes');
  const [untickConfirming, setUntickConfirming] = useState(false);

  // Access Control Mode
  const [accessMode, setAccessMode] = useState<'segment' | 'distributor'>('segment');
  const [accessModeSaving, setAccessModeSaving] = useState(false);

  // Bulk Upload Modal State
  const [bulkModalOpen, setBulkModalOpen] = useState(false);
  const [bulkFile, setBulkFile] = useState<File | null>(null);
  const [bulkPreview, setBulkPreview] = useState<any | null>(null);
  const [bulkReplace, setBulkReplace] = useState(true);
  const [bulkParsing, setBulkParsing] = useState(false);
  const [bulkUploading, setBulkUploading] = useState(false);
  const [bulkError, setBulkError] = useState<string | null>(null);

  // Dialog State
  const [dialog, setDialog] = useState<DialogMode>(null);
  const [target, setTarget] = useState<ManagedUser | null>(null);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  // Distributor edit state
  const [allDistributors, setAllDistributors] = useState<
    Array<{ id: number; name: string; segment: string }>
  >([]);
  const [selectedDistributorIds, setSelectedDistributorIds] = useState<number[]>([]);
  const [distSearch, setDistSearch] = useState('');
  const [newDistributorName, setNewDistributorName] = useState('');
  const [addingDistributor, setAddingDistributor] = useState(false);
  const [renameDistributorRows, setRenameDistributorRows] = useState<Array<{ id: number; name: string }>>([]);
  const [credentialsMenuId, setCredentialsMenuId] = useState<number | null>(null);
  const [collapsedDistSegments, setCollapsedDistSegments] = useState<string[]>([]);

  // Form State
  const [fullName, setFullName] = useState('');
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [title, setTitle] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [createRole, setCreateRole] = useState<'admin' | 'user'>('user');
  const [selectedSegments, setSelectedSegments] = useState<string[]>([]);

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

  const loadUsers = useCallback(async () => {
    if (!isAdminRole(userRole)) return;
    setLoading(true);
    setError(null);
    try {
      const data = await UserManagementService.list(query);
      setRows(data.data);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load users');
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, [query, userRole]);

  const loadMatrix = useCallback(async () => {
    if (!isAdminRole(userRole)) return;
    setMatrixLoading(true);
    try {
      const res = await UserManagementService.getSegmentMatrix();
      setMatrixData(res);
    } catch (err) {
      console.error('Failed to load matrix', err);
    } finally {
      setMatrixLoading(false);
    }
  }, [userRole]);

  const loadAccessMode = useCallback(async () => {
    if (!isAdminRole(userRole)) return;
    try {
      const mode = await UserManagementService.getAccessMode();
      setAccessMode(mode);
    } catch (err) {
      console.error('Failed to load access mode', err);
    }
  }, [userRole]);

  useEffect(() => {
    loadUsers();
    loadMatrix();
    loadAccessMode();
  }, [loadUsers, loadMatrix, loadAccessMode]);

  const handleAccessModeChange = async (mode: 'segment' | 'distributor') => {
    if (mode === accessMode || accessModeSaving) return;
    setAccessModeSaving(true);
    setError(null);
    try {
      const saved = await UserManagementService.setAccessMode(mode);
      setAccessMode(saved);
      setSuccessMsg(
        saved === 'segment'
          ? 'Access Control Mode set to Segment Access'
          : 'Access Control Mode set to Distributor Specific'
      );
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to update Access Control Mode');
    } finally {
      setAccessModeSaving(false);
    }
  };

  if (!isAdminRole(userRole)) {
    return <Navigate to="/" replace />;
  }

  const toggleRowExpand = (userId: number) => {
    setExpandedUserIds(prev =>
      prev.includes(userId) ? prev.filter(id => id !== userId) : [...prev, userId]
    );
  };

  const handleToggleMatrixCell = async (
    userId: number,
    segment: string,
    currentEnabled: boolean,
  ) => {
    // Untick → confirmation modal first (do not mutate yet)
    if (currentEnabled) {
      const row = matrixData.rows.find(r => r.id === userId);
      setRetainHistoryChoice('yes');
      setUntickConfirm({
        userId,
        userName: row?.fullName || 'this employee',
        segment,
      });
      return;
    }

    // Tick → assign immediately
    const key = `${userId}-${segment}`;
    setMatrixSaving(prev => ({ ...prev, [key]: true }));

    setMatrixData(prev => ({
      ...prev,
      rows: prev.rows.map(r => {
        if (r.id === userId) {
          return {
            ...r,
            segments: {
              ...r.segments,
              [segment]: true,
            },
          };
        }
        return r;
      }),
    }));

    try {
      await UserManagementService.toggleMatrixCell(userId, segment, true);
      await loadUsers();
    } catch (err) {
      setMatrixData(prev => ({
        ...prev,
        rows: prev.rows.map(r => {
          if (r.id === userId) {
            return {
              ...r,
              segments: {
                ...r.segments,
                [segment]: false,
              },
            };
          }
          return r;
        }),
      }));
      setError('Failed to update segment permission');
    } finally {
      setMatrixSaving(prev => ({ ...prev, [key]: false }));
    }
  };

  const confirmUntickSegment = async () => {
    if (!untickConfirm) return;
    const { userId, segment } = untickConfirm;
    const key = `${userId}-${segment}`;
    const retainHistory = retainHistoryChoice === 'yes';
    setUntickConfirming(true);
    setMatrixSaving(prev => ({ ...prev, [key]: true }));

    setMatrixData(prev => ({
      ...prev,
      rows: prev.rows.map(r => {
        if (r.id === userId) {
          return {
            ...r,
            segments: {
              ...r.segments,
              [segment]: false,
            },
          };
        }
        return r;
      }),
    }));

    try {
      await UserManagementService.toggleMatrixCell(userId, segment, false, retainHistory);
      setUntickConfirm(null);
      await loadUsers();
    } catch (err) {
      setMatrixData(prev => ({
        ...prev,
        rows: prev.rows.map(r => {
          if (r.id === userId) {
            return {
              ...r,
              segments: {
                ...r.segments,
                [segment]: true,
              },
            };
          }
          return r;
        }),
      }));
      setError('Failed to remove segment permission');
    } finally {
      setUntickConfirming(false);
      setMatrixSaving(prev => ({ ...prev, [key]: false }));
    }
  };

  const openCreate = () => {
    setTarget(null);
    setFullName('');
    setUsername('');
    setEmail('');
    setTitle('');
    setPassword('');
    setConfirmPassword('');
    setCreateRole('user');
    setSelectedSegments([]);
    setFormError(null);
    setDialog('create');
  };

  const openSegments = (user: ManagedUser) => {
    setTarget(user);
    setSelectedSegments((user.segments || []).filter(s => s && s !== '*'));
    setEmail(user.email || '');
    setFormError(null);
    setDialog('segments');
  };

  const openPassword = (user: ManagedUser) => {
    setTarget(user);
    setPassword('');
    setConfirmPassword('');
    setFormError(null);
    setDialog('password');
  };

  const openUsername = (user: ManagedUser) => {
    setTarget(user);
    setUsername(user.username || '');
    setFormError(null);
    setDialog('username');
  };

  const openEmail = (user: ManagedUser) => {
    setTarget(user);
    setEmail(user.email || '');
    setFormError(null);
    setDialog('email');
  };

  const distributorsBySegment = useMemo(() => {
    const q = distSearch.trim().toLowerCase();
    const filtered = allDistributors.filter(d => !q || d.name.toLowerCase().includes(q));
    return ALL_SEGMENTS.map(segment => ({
      segment,
      items: filtered
        .filter(d => d.segment === segment)
        .sort((a, b) => a.name.localeCompare(b.name)),
    }));
  }, [allDistributors, distSearch]);

  const resolveDistributorSegment = (
    name: string,
    id: number,
    segmentById: Map<number, string>,
  ): string => {
    const mapped = segmentById.get(id);
    if (mapped && ALL_SEGMENTS.includes(mapped)) return mapped;
    const key = (name || '').toLowerCase();
    // Known Construction accounts (Admin / FYIP / export)
    if (key.includes('redachem')) return 'Construction';
    return 'Construction';
  };

  const openDistributors = async (user: {
    id: number;
    full_name?: string;
    fullName?: string;
    username?: string;
    email?: string;
    role?: string;
    segments?: string[];
    associatedDistributorIds?: number[];
    distributor_ids?: number[];
  }) => {
    setTarget({
      id: user.id,
      full_name: user.full_name || user.fullName || '',
      username: user.username || '',
      email: user.email || '',
      role: (user.role as ManagedUser['role']) || 'user',
      is_active: true,
      segments: user.segments || [],
      distributor_ids: user.associatedDistributorIds || user.distributor_ids || [],
    } as ManagedUser);
    setFormError(null);
    setDistSearch('');
    setNewDistributorName('');
    setCollapsedDistSegments([]);
    setBusy(true);
    try {
      let matrixRows = matrixData.rows || [];
      try {
        const fresh = await UserManagementService.getSegmentMatrix();
        setMatrixData(fresh);
        matrixRows = fresh.rows || [];
      } catch {
        /* keep existing matrix */
      }

      const segmentById = new Map<number, string>();
      const applyOwner = (distributorIds: number[] | undefined, segments: string[] | undefined) => {
        const primary = (segments || []).find(s => s && s !== '*' && ALL_SEGMENTS.includes(s));
        if (!primary || !distributorIds?.length) return;
        for (const id of distributorIds) {
          if (typeof id === 'number' && id > 0 && !segmentById.has(id)) {
            segmentById.set(id, primary);
          }
        }
      };

      // Sales Owners: their segment owns their distributors
      for (const u of rows) {
        if (u.role === 'admin' || u.role === 'super_admin') continue;
        applyOwner(u.distributor_ids, u.segments);
      }
      for (const u of matrixRows) {
        if (u.role === 'admin' || u.role === 'super_admin') continue;
        const fromAssigned: string[] = Array.isArray(u.assignedSegments) ? u.assignedSegments : [];
        const fromMap: string[] = Object.entries(u.segments || {})
          .filter(([, enabled]) => Boolean(enabled))
          .map(([seg]) => String(seg));
        applyOwner(u.associatedDistributorIds, fromAssigned.length ? fromAssigned : fromMap);
      }

      // Admin / Debabrata linked distributors → Construction (e.g. REDACHEM VIETNAM)
      for (const u of rows) {
        if (u.role !== 'admin' && u.role !== 'super_admin') continue;
        applyOwner(u.distributor_ids, ['Construction']);
      }
      for (const u of matrixRows) {
        if (u.role !== 'admin' && u.role !== 'super_admin') continue;
        applyOwner(u.associatedDistributorIds, ['Construction']);
      }

      const list = await DistributorService.list({ active_only: true, limit: 500 });
      const opts = (list.data || []).map(d => {
        const name = (d.company || d.name || `Distributor #${d.id}`).trim();
        return {
          id: d.id,
          name,
          segment: resolveDistributorSegment(name, d.id, segmentById),
        };
      });
      setAllDistributors(opts);
      const preselected =
        user.associatedDistributorIds?.length
          ? [...user.associatedDistributorIds]
          : user.distributor_ids?.length
            ? [...user.distributor_ids]
            : [];
      setSelectedDistributorIds(preselected);
      setDialog('distributors');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load distributors');
    } finally {
      setBusy(false);
    }
  };

  const openRenameDistributors = (user: {
    id: number;
    fullName?: string;
    full_name?: string;
    username?: string;
    email?: string;
    role?: string;
    associatedDistributors?: string[];
    associatedDistributorIds?: number[];
  }) => {
    const ids = user.associatedDistributorIds || [];
    const names = user.associatedDistributors || [];
    if (!ids.length) {
      setError('No distributors to rename. Assign them from Employee Accounts → Distributors.');
      return;
    }
    setTarget({
      id: user.id,
      full_name: user.full_name || user.fullName || '',
      username: user.username || '',
      email: user.email || '',
      role: (user.role as ManagedUser['role']) || 'user',
      is_active: true,
    } as ManagedUser);
    setRenameDistributorRows(
      ids.map((id, i) => ({
        id,
        name: (names[i] || `Distributor #${id}`).trim(),
      })),
    );
    setFormError(null);
    setDialog('renameDistributors');
  };

  const handleAddDistributorInline = async () => {
    const company = newDistributorName.trim();
    if (!company) {
      setFormError('Enter a distributor company name to add.');
      return;
    }
    setAddingDistributor(true);
    setFormError(null);
    try {
      const created = await DistributorService.create({
        name: company,
        company,
        is_active: true,
      });
      const label = (created.company || created.name || company).trim();
      const ownerSeg =
        (target?.segments || []).find(s => s && s !== '*' && ALL_SEGMENTS.includes(s)) ||
        (rows.find(r => r.id === target?.id)?.segments || []).find(
          s => s && s !== '*' && ALL_SEGMENTS.includes(s),
        ) ||
        (target?.role === 'admin' || target?.role === 'super_admin' ? 'Construction' : 'Rubber');
      setAllDistributors(prev => {
        if (prev.some(d => d.id === created.id)) return prev;
        return [...prev, { id: created.id, name: label, segment: ownerSeg }].sort((a, b) =>
          a.name.localeCompare(b.name),
        );
      });
      setSelectedDistributorIds(prev =>
        prev.includes(created.id) ? prev : [...prev, created.id],
      );
      setNewDistributorName('');
      setSuccessMsg(`Added "${label}" to Master and selected for assignment`);
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : 'Failed to add distributor');
    } finally {
      setAddingDistributor(false);
    }
  };

  const handleSaveDistributors = async (e: FormEvent) => {
    e.preventDefault();
    if (!target) return;
    setBusy(true);
    setFormError(null);
    try {
      await UserManagementService.assignDistributors(target.id, selectedDistributorIds);
      setSuccessMsg(`Updated distributors for ${target.full_name}`);
      setDialog(null);
      await loadUsers();
      await loadMatrix();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : 'Failed to save distributors');
    } finally {
      setBusy(false);
    }
  };

  const handleSaveRenamedDistributors = async (e: FormEvent) => {
    e.preventDefault();
    if (!target) return;
    const cleaned = renameDistributorRows.map(r => ({
      id: r.id,
      name: r.name.trim(),
    }));
    if (cleaned.some(r => !r.name)) {
      setFormError('Distributor name cannot be empty.');
      return;
    }
    setBusy(true);
    setFormError(null);
    try {
      await Promise.all(
        cleaned.map(r =>
          DistributorService.update(r.id, {
            company: r.name,
            name: r.name,
          }),
        ),
      );
      setSuccessMsg(`Updated distributor name(s) for ${target.full_name}`);
      setDialog(null);
      await loadUsers();
      await loadMatrix();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : 'Failed to rename distributors');
    } finally {
      setBusy(false);
    }
  };

  const handlePromoteToAdmin = async (user: ManagedUser) => {
    if (!window.confirm(`Promote ${user.full_name} to Admin? They will see all data.`)) return;
    try {
      await UserManagementService.setRole(user.id, 'admin');
      setSuccessMsg(`${user.full_name} is now an Admin`);
      await loadUsers();
      await loadMatrix();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to promote user');
    }
  };

  const handleDemoteToSalesOwner = async (user: ManagedUser) => {
    if (!window.confirm(`Demote ${user.full_name} to Sales Owner?`)) return;
    try {
      await UserManagementService.setRole(user.id, 'user');
      setSuccessMsg(`${user.full_name} is now a Sales Owner`);
      await loadUsers();
      await loadMatrix();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to demote user');
    }
  };

  const handleFileChange = async (file: File | null) => {
    setBulkFile(file);
    setBulkPreview(null);
    setBulkError(null);
    if (!file) return;

    setBulkParsing(true);
    try {
      const preview = await UserManagementService.previewBulkPersonaImport(file);
      setBulkPreview(preview);
    } catch (err) {
      setBulkError(err instanceof ApiError ? err.message : 'Failed to parse Excel file');
      setBulkFile(null);
    } finally {
      setBulkParsing(false);
    }
  };

  const handleExecuteBulkImport = async () => {
    if (!bulkFile) return;
    setBulkUploading(true);
    setBulkError(null);
    try {
      const result = await UserManagementService.executeBulkPersonaImport(bulkFile, bulkReplace);
      setSuccessMsg(result.message || 'Bulk employee mapping imported successfully!');
      setBulkModalOpen(false);
      setBulkFile(null);
      setBulkPreview(null);
      await loadUsers();
      await loadMatrix();
    } catch (err) {
      setBulkError(err instanceof ApiError ? err.message : 'Bulk import failed');
    } finally {
      setBulkUploading(false);
    }
  };

  const handleDownloadSample = async () => {
    try {
      await UserManagementService.downloadSampleFormat();
    } catch (err) {
      setError('Failed to download sample format');
    }
  };

  const handleSaveCreate = async (e: FormEvent) => {
    e.preventDefault();
    if (!fullName || !username || !password) {
      setFormError('Full name, username, and password are required.');
      return;
    }
    if (password !== confirmPassword) {
      setFormError('Passwords do not match.');
      return;
    }
    setBusy(true);
    setFormError(null);
    try {
      const created = await UserManagementService.create({
        full_name: fullName.trim(),
        username: username.trim(),
        email: email.trim() || undefined,
        title: title.trim() || 'Sales Owner',
        password,
        role: createRole,
        is_active: true,
      });
      if (selectedSegments.length > 0) {
        await UserManagementService.assignSegments(created.id, selectedSegments);
      }
      setDialog(null);
      setSuccessMsg(`Employee account created for ${created.full_name}`);
      await loadUsers();
      await loadMatrix();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : 'Failed to create employee');
    } finally {
      setBusy(false);
    }
  };

  const handleSaveSegments = async (e: FormEvent) => {
    e.preventDefault();
    if (!target) return;
    setBusy(true);
    setFormError(null);
    try {
      if (email.trim() && email.trim() !== target.email) {
        await UserManagementService.updateUser(target.id, { email: email.trim() });
      }
      await UserManagementService.assignSegments(target.id, selectedSegments);
      setDialog(null);
      setSuccessMsg(`Persona updated for ${target.full_name}`);
      await loadUsers();
      await loadMatrix();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : 'Failed to update persona');
    } finally {
      setBusy(false);
    }
  };

  const handleSavePassword = async (e: FormEvent) => {
    e.preventDefault();
    if (!target) return;
    if (!password) {
      setFormError('Password is required.');
      return;
    }
    if (password !== confirmPassword) {
      setFormError('Passwords do not match.');
      return;
    }
    setBusy(true);
    setFormError(null);
    try {
      await UserManagementService.changePassword(target.id, password, confirmPassword);
      setDialog(null);
      setSuccessMsg(`Password updated for ${target.username}`);
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : 'Failed to update password');
    } finally {
      setBusy(false);
    }
  };

  const handleSaveUsername = async (e: FormEvent) => {
    e.preventDefault();
    if (!target) return;
    const next = username.trim().toLowerCase();
    if (!next || next.length < 3) {
      setFormError('Username must be at least 3 characters.');
      return;
    }
    setBusy(true);
    setFormError(null);
    try {
      await UserManagementService.updateUsername(target.id, next);
      setDialog(null);
      setSuccessMsg(`Username updated to "${next}"`);
      await loadUsers();
      await loadMatrix();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : 'Failed to update username');
    } finally {
      setBusy(false);
    }
  };

  const handleSaveEmail = async (e: FormEvent) => {
    e.preventDefault();
    if (!target) return;
    const next = email.trim().toLowerCase();
    if (!next || !next.includes('@')) {
      setFormError('Enter a valid email address.');
      return;
    }
    setBusy(true);
    setFormError(null);
    try {
      await UserManagementService.updateUser(target.id, { email: next });
      setDialog(null);
      setSuccessMsg(`Email updated to "${next}"`);
      await loadUsers();
      await loadMatrix();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : 'Failed to update email');
    } finally {
      setBusy(false);
    }
  };

  const handleDeleteUser = async (userToDelete: any) => {
    if (userToDelete.role === 'admin' || userToDelete.role === 'super_admin') {
      setError('Admin accounts cannot be deleted');
      return;
    }
    const name = userToDelete.fullName || userToDelete.full_name || userToDelete.username;
    if (!window.confirm(`Are you sure you want to delete employee "${name}"?`)) return;
    try {
      await UserManagementService.remove(userToDelete.id);
      setSuccessMsg(`Employee account "${name}" deleted`);
      await loadUsers();
      await loadMatrix();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to delete user');
    }
  };

  const handleToggleStatus = async (user: ManagedUser) => {
    try {
      await UserManagementService.setStatus(user.id, !user.is_active);
      setSuccessMsg(`Account status updated for ${user.full_name}`);
      await loadUsers();
      await loadMatrix();
    } catch (err) {
      setError('Failed to toggle user status');
    }
  };

  const handleOutlookSyncPermission = async (
    user: ManagedUser,
    outlook_sync_permission: 'none' | 'own' | 'all',
  ) => {
    if ((user.outlook_sync_permission || (user.role === 'admin' || user.role === 'super_admin' ? 'all' : 'own')) === outlook_sync_permission) {
      return;
    }
    try {
      setBusy(true);
      await UserManagementService.setOutlookSyncPermission(user.id, outlook_sync_permission);
      setSuccessMsg(`Sync Outlook permission updated for ${user.full_name}`);
      await loadUsers();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to update Sync Outlook permission');
    } finally {
      setBusy(false);
    }
  };

  const handleExport = async () => {
    setExporting(true);
    try {
      await UserManagementService.exportExcel(query);
    } catch (err) {
      setError('Export failed');
    } finally {
      setExporting(false);
    }
  };

  return (
    <div style={{ padding: '24px 32px', maxWidth: 1440, margin: '0 auto' }}>
      {/* Page Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 20, flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h1 style={{ fontSize: '1.5rem', fontWeight: 700, color: '#111827', margin: 0, letterSpacing: '-0.02em' }}>
            Persona Management
          </h1>
          <p style={{ color: '#6B7280', fontSize: '0.875rem', marginTop: 4, margin: 0 }}>
            Master access control for sales owners, segment permissions, and distributor assignments.
          </p>
        </div>

        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <button
            onClick={handleDownloadSample}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              padding: '9px 14px',
              borderRadius: 8,
              fontSize: '0.8125rem',
              fontWeight: 600,
              background: 'white',
              border: `1px solid ${BORDER}`,
              color: BLUE,
              cursor: 'pointer',
            }}
            title="Download sample Excel template"
          >
            <FileSpreadsheet size={15} />
            Sample Format
          </button>

          <button
            onClick={() => {
              setBulkFile(null);
              setBulkPreview(null);
              setBulkReplace(false);
              setBulkError(null);
              setBulkModalOpen(true);
            }}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              padding: '9px 16px',
              borderRadius: 8,
              fontSize: '0.8125rem',
              fontWeight: 600,
              background: TEAL,
              color: 'white',
              border: 'none',
              cursor: 'pointer',
              boxShadow: '0 1px 2px rgba(0,0,0,0.05)',
            }}
          >
            <Upload size={16} />
            Bulk Upload Employee Mapping
          </button>

          <button
            onClick={handleExport}
            disabled={exporting}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              padding: '9px 14px',
              borderRadius: 8,
              fontSize: '0.8125rem',
              fontWeight: 600,
              background: 'white',
              border: `1px solid ${BORDER}`,
              color: '#374151',
              cursor: exporting ? 'not-allowed' : 'pointer',
            }}
          >
            <Download size={15} />
            {exporting ? 'Exporting...' : 'Export Excel'}
          </button>

          <button
            onClick={openCreate}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              padding: '9px 16px',
              borderRadius: 8,
              fontSize: '0.8125rem',
              fontWeight: 600,
              background: BLUE,
              color: 'white',
              border: 'none',
              cursor: 'pointer',
            }}
          >
            <Plus size={16} />
            Add Employee
          </button>
        </div>
      </div>

      {error && <StatusBanner message={error} type="error" onClose={() => setError(null)} style={{ marginBottom: 16 }} />}
      {successMsg && <StatusBanner message={successMsg} type="success" onClose={() => setSuccessMsg(null)} style={{ marginBottom: 16 }} />}

      {/* Access Control Mode */}
      <div
        style={{
          background: 'white',
          border: `1px solid ${BORDER}`,
          borderRadius: 12,
          padding: '20px 24px',
          marginBottom: 20,
          boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
          <ShieldCheck size={20} color={BLUE} />
          <h2 style={{ margin: 0, fontSize: '1.0625rem', fontWeight: 700, color: '#111827' }}>
            Access Control Mode
          </h2>
        </div>
        <p style={{ margin: '0 0 16px', fontSize: '0.8125rem', color: '#6B7280', maxWidth: 720 }}>
          Controls what Sales Owners can see across Emails, Consolidated Data, Dashboard, and Visualizations.
          Admin always sees everything.
        </p>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <button
            type="button"
            disabled={accessModeSaving}
            onClick={() => handleAccessModeChange('segment')}
            style={{
              flex: '1 1 280px',
              textAlign: 'left',
              padding: '14px 16px',
              borderRadius: 10,
              border: accessMode === 'segment' ? `2px solid ${BLUE}` : `1px solid ${BORDER}`,
              background: accessMode === 'segment' ? 'rgba(31,95,168,0.06)' : 'white',
              cursor: accessModeSaving ? 'not-allowed' : 'pointer',
            }}
          >
            <div style={{ fontWeight: 700, color: '#111827', fontSize: '0.9375rem', marginBottom: 4 }}>
              Segment Access <span style={{ fontSize: '0.75rem', fontWeight: 600, color: TEAL }}>(Default)</span>
            </div>
            <div style={{ fontSize: '0.8125rem', color: '#6B7280', lineHeight: 1.45 }}>
              Sales Owners can view <strong>all distributors</strong> belonging to their assigned segment.
            </div>
          </button>
          <button
            type="button"
            disabled={accessModeSaving}
            onClick={() => handleAccessModeChange('distributor')}
            style={{
              flex: '1 1 280px',
              textAlign: 'left',
              padding: '14px 16px',
              borderRadius: 10,
              border: accessMode === 'distributor' ? `2px solid ${BLUE}` : `1px solid ${BORDER}`,
              background: accessMode === 'distributor' ? 'rgba(31,95,168,0.06)' : 'white',
              cursor: accessModeSaving ? 'not-allowed' : 'pointer',
            }}
          >
            <div style={{ fontWeight: 700, color: '#111827', fontSize: '0.9375rem', marginBottom: 4 }}>
              Distributor Specific
            </div>
            <div style={{ fontSize: '0.8125rem', color: '#6B7280', lineHeight: 1.45 }}>
              Sales Owners can view <strong>only distributors explicitly assigned</strong> to them.
            </div>
          </button>
        </div>
      </div>

      {/* View Tabs */}
      <div style={{ display: 'flex', borderBottom: `1px solid ${BORDER}`, marginBottom: 20 }}>
        <button
          onClick={() => setActiveTab('matrix')}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 8,
            padding: '12px 20px',
            fontSize: '0.9375rem',
            fontWeight: 600,
            border: 'none',
            borderBottom: activeTab === 'matrix' ? `2px solid ${BLUE}` : '2px solid transparent',
            color: activeTab === 'matrix' ? BLUE : '#6B7280',
            background: 'transparent',
            cursor: 'pointer',
          }}
        >
          <Grid size={18} />
          Segment Permission Matrix
        </button>

        <button
          onClick={() => setActiveTab('users')}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 8,
            padding: '12px 20px',
            fontSize: '0.9375rem',
            fontWeight: 600,
            border: 'none',
            borderBottom: activeTab === 'users' ? `2px solid ${BLUE}` : '2px solid transparent',
            color: activeTab === 'users' ? BLUE : '#6B7280',
            background: 'transparent',
            cursor: 'pointer',
          }}
        >
          <List size={18} />
          Employee Accounts ({rows.length})
        </button>
      </div>

      {/* TAB 1: SEGMENT PERMISSION MATRIX */}
      {activeTab === 'matrix' && (
        <div style={{ background: 'white', border: `1px solid ${BORDER}`, borderRadius: 12, overflow: 'hidden', boxShadow: '0 1px 3px rgba(0,0,0,0.05)' }}>
          <div style={{ padding: '16px 24px', borderBottom: `1px solid ${BORDER}`, background: '#F9FAFB', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 700, color: '#111827', letterSpacing: '-0.01em' }}>
                Persona Permission Matrix
              </h3>
              <p style={{ margin: '3px 0 0', fontSize: '0.8125rem', color: '#6B7280' }}>
                Select checkboxes to configure segment permissions. Click a sales team member to view associated distributors.
              </p>
            </div>
          </div>

          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.875rem' }}>
              <colgroup>
                <col style={{ width: '35%' }} />
                <col style={{ width: '13%' }} />
                <col style={{ width: '13%' }} />
                <col style={{ width: '13%' }} />
                <col style={{ width: '13%' }} />
                <col style={{ width: '13%' }} />
              </colgroup>
              <thead>
                <tr style={{ background: '#F8FAFC', borderBottom: `2px solid ${BORDER}` }}>
                  <th style={{ padding: '14px 20px', fontWeight: 700, color: '#1E293B', fontSize: '0.875rem' }}>
                    Sales Team Member
                  </th>
                  {ALL_SEGMENTS.map(seg => (
                    <th key={seg} style={{ padding: '14px 12px', fontWeight: 700, color: BLUE, textAlign: 'center', fontSize: '0.875rem' }}>
                      {seg}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {matrixLoading ? (
                  <tr>
                    <td colSpan={6} style={{ padding: 48, textAlign: 'center', color: '#6B7280' }}>
                      Loading permission matrix...
                    </td>
                  </tr>
                ) : matrixData.rows.length === 0 ? (
                  <tr>
                    <td colSpan={6} style={{ padding: 48, textAlign: 'center', color: '#6B7280' }}>
                      No sales team members found. Click <strong>Bulk Upload Employee Mapping</strong> to import Excel data.
                    </td>
                  </tr>
                ) : (
                  matrixData.rows.map(user => {
                    const isAdmin = user.role === 'admin' || user.role === 'super_admin';
                    const isExpanded = expandedUserIds.includes(user.id);
                    const distributorsList: string[] = Array.isArray(user.associatedDistributors)
                      ? user.associatedDistributors
                      : [];
                    const distCount = isAdmin && distributorsList.length === 0
                      ? 'All Distributors (Admin)'
                      : `${distributorsList.length} Distributor${distributorsList.length === 1 ? '' : 's'}`;

                    return (
                      <Fragment key={user.id}>
                        <tr
                          onClick={() => toggleRowExpand(user.id)}
                          style={{
                            background: isExpanded ? '#F0F9FF' : 'white',
                            cursor: 'pointer',
                            borderBottom: `1px solid ${BORDER}`,
                            transition: 'background 0.15s ease-in-out',
                          }}
                        >
                          <td style={{ padding: '14px 20px', fontWeight: 600, color: '#0F172A' }}>
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%' }}>
                              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                                <span style={{ color: BLUE, display: 'flex', alignItems: 'center' }}>
                                  {isExpanded ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
                                </span>
                                <div>
                                  <div style={{ fontSize: '0.9375rem', fontWeight: 600, color: '#0F172A' }}>{user.fullName}</div>
                                  <div style={{ fontSize: '0.75rem', color: '#64748B', fontWeight: 500, marginTop: 2 }}>
                                    @{user.username} &bull; <span style={{ color: BLUE }}>{distCount}</span>
                                  </div>
                                </div>
                              </div>

                              {!isAdmin && (
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    handleDeleteUser(user);
                                  }}
                                  style={{
                                    background: 'none',
                                    border: 'none',
                                    cursor: 'pointer',
                                    color: '#94A3B8',
                                    padding: '4px 6px',
                                    borderRadius: 6,
                                    display: 'inline-flex',
                                    alignItems: 'center',
                                    gap: 4,
                                    fontSize: '0.75rem',
                                    fontWeight: 500,
                                    transition: 'all 0.15s ease',
                                  }}
                                  onMouseEnter={(e) => {
                                    e.currentTarget.style.color = '#EF4444';
                                    e.currentTarget.style.background = 'rgba(239,68,68,0.08)';
                                  }}
                                  onMouseLeave={(e) => {
                                    e.currentTarget.style.color = '#94A3B8';
                                    e.currentTarget.style.background = 'none';
                                  }}
                                  title={`Delete ${user.fullName}`}
                                >
                                  <Trash2 size={15} />
                                </button>
                              )}
                            </div>
                          </td>
                          {ALL_SEGMENTS.map(segment => {
                            const isEnabled = Boolean(user.segments?.[segment]);
                            const key = `${user.id}-${segment}`;
                            const isBusy = Boolean(matrixSaving[key]);

                            return (
                              <td
                                key={segment}
                                style={{ padding: '14px 12px', textAlign: 'center', verticalAlign: 'middle' }}
                                onClick={(e) => e.stopPropagation()}
                              >
                                {isAdmin ? (
                                  <span title="Admins have access to all segments" style={{ display: 'inline-flex', alignItems: 'center', gap: 4, color: '#059669', fontSize: '0.75rem', fontWeight: 700 }}>
                                    <ShieldCheck size={16} /> All
                                  </span>
                                ) : (
                                  <input
                                    type="checkbox"
                                    checked={isEnabled}
                                    disabled={isBusy || !user.isActive}
                                    onChange={() => handleToggleMatrixCell(user.id, segment, isEnabled)}
                                    style={{
                                      width: 18,
                                      height: 18,
                                      cursor: isBusy || !user.isActive ? 'not-allowed' : 'pointer',
                                      accentColor: BLUE,
                                    }}
                                  />
                                )}
                              </td>
                            );
                          })}
                        </tr>

                        {/* ASSOCIATED DISTRIBUTORS DROPDOWN */}
                        {isExpanded && (
                          <tr style={{ background: '#F8FAFC', borderBottom: `1px solid ${BORDER}` }}>
                            <td colSpan={6} style={{ padding: '14px 24px 18px 48px' }}>
                              <div style={{ background: 'white', padding: '14px 20px', borderRadius: 8, border: `1px solid ${BORDER}`, boxShadow: '0 1px 3px rgba(0,0,0,0.04)' }}>
                                <div style={{ fontSize: '0.75rem', fontWeight: 700, color: '#334155', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 10, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 6 }}>
                                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                                    <Building2 size={14} style={{ color: BLUE }} />
                                    Associated Distributors for {user.fullName}
                                  </span>
                                  {distributorsList.length > 0 && (
                                    <button
                                      type="button"
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        openRenameDistributors(user);
                                      }}
                                      style={{
                                        display: 'inline-flex',
                                        alignItems: 'center',
                                        gap: 5,
                                        padding: '5px 10px',
                                        borderRadius: 6,
                                        border: `1px solid ${BLUE}`,
                                        background: 'rgba(31,95,168,0.06)',
                                        color: BLUE,
                                        fontSize: '0.75rem',
                                        fontWeight: 600,
                                        cursor: 'pointer',
                                      }}
                                    >
                                      <Pencil size={13} />
                                      Edit Names
                                    </button>
                                  )}
                                </div>
                                {isAdmin && distributorsList.length === 0 ? (
                                  <div style={{ fontSize: '0.8125rem', color: '#059669', fontWeight: 600 }}>
                                    Super Admin / Admin — Full access to all distributors.
                                  </div>
                                ) : distributorsList.length === 0 ? (
                                  <div style={{ fontSize: '0.8125rem', color: '#94A3B8', fontStyle: 'italic' }}>
                                    No distributors associated. Assign them from Employee Accounts → Distributors.
                                  </div>
                                ) : (
                                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                                    {isAdmin && (
                                      <span style={{ fontSize: '0.75rem', fontWeight: 600, color: '#059669', alignSelf: 'center' }}>
                                        Admin · explicit links:
                                      </span>
                                    )}
                                    {distributorsList.map((distName, idx) => (
                                      <span
                                        key={`${user.associatedDistributorIds?.[idx] ?? distName}-${idx}`}
                                        style={{
                                          display: 'inline-flex',
                                          alignItems: 'center',
                                          gap: 5,
                                          fontSize: '0.8125rem',
                                          fontWeight: 600,
                                          color: BLUE,
                                          background: 'rgba(31,95,168,0.08)',
                                          padding: '5px 12px',
                                          borderRadius: 6,
                                          border: `1px solid rgba(31,95,168,0.18)`,
                                        }}
                                      >
                                        <Building2 size={13} />
                                        {distName}
                                      </span>
                                    ))}
                                  </div>
                                )}
                              </div>
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* TAB 2: EMPLOYEE ACCOUNTS LIST */}
      {activeTab === 'users' && (
        <div style={{ background: 'white', border: `1px solid ${BORDER}`, borderRadius: 12, overflow: 'hidden', boxShadow: '0 1px 3px rgba(0,0,0,0.05)' }}>
          {/* Search & Filter Bar */}
          <div style={{ padding: 16, borderBottom: `1px solid ${BORDER}`, display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center', background: '#F9FAFB' }}>
            <div style={{ position: 'relative', flex: 1, minWidth: 260 }}>
              <Search size={16} style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: '#9CA3AF' }} />
              <input
                type="text"
                value={searchInput}
                onChange={e => setSearchInput(e.target.value)}
                placeholder="Search employees by name, username, or email..."
                style={{ ...inputStyle, paddingLeft: 36 }}
              />
            </div>

            <select value={roleFilter} onChange={e => setRoleFilter(e.target.value)} style={{ ...inputStyle, width: 140 }}>
              <option value="All">All Roles</option>
              <option value="admin">Admin</option>
              <option value="user">Sales Owner</option>
            </select>

            <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)} style={{ ...inputStyle, width: 140 }}>
              <option value="All">All Status</option>
              <option value="Active">Active</option>
              <option value="Inactive">Inactive</option>
            </select>
          </div>

          {/* Table */}
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.875rem' }}>
              <thead>
                <tr style={{ background: '#F9FAFB', borderBottom: `1px solid ${BORDER}` }}>
                  <th style={{ padding: '12px 20px', fontWeight: 600, color: '#374151' }}>Employee Name</th>
                  <th style={{ padding: '12px 16px', fontWeight: 600, color: '#374151' }}>Username</th>
                  <th style={{ padding: '12px 16px', fontWeight: 600, color: '#374151' }}>Email</th>
                  <th style={{ padding: '12px 16px', fontWeight: 600, color: '#374151' }}>Status</th>
                  <th style={{ padding: '12px 16px', fontWeight: 600, color: '#374151' }}>Segment</th>
                  <th style={{ padding: '12px 16px', fontWeight: 600, color: '#374151' }}>Assigned Distributors</th>
                  <th style={{ padding: '12px 16px', fontWeight: 600, color: '#374151', minWidth: 220 }}>Sync Outlook</th>
                  <th style={{ padding: '12px 20px', fontWeight: 600, color: '#374151', textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td colSpan={8} style={{ padding: 40, textAlign: 'center', color: '#6B7280' }}>
                      Loading employee accounts...
                    </td>
                  </tr>
                ) : rows.length === 0 ? (
                  <tr>
                    <td colSpan={8} style={{ padding: 40, textAlign: 'center', color: '#6B7280' }}>
                      No employee accounts found matching criteria.
                    </td>
                  </tr>
                ) : (
                  rows.map(user => {
                    const isAdmin = user.role === 'admin' || user.role === 'super_admin';
                    const segments = (user.segments || []).filter(s => s && s !== '*');
                    const distCount = user.assigned_distributor_count ?? user.distributor_ids?.length ?? 0;
                    const syncPerm =
                      user.outlook_sync_permission ||
                      (isAdmin ? 'all' : 'own');

                    return (
                      <tr key={user.id} style={{ borderBottom: `1px solid ${BORDER}`, background: 'white' }}>
                        <td style={{ padding: '14px 20px', fontWeight: 600, color: '#111827' }}>
                          {user.full_name}
                          <div style={{ marginTop: 4 }}>
                            <RoleBadge role={user.role} />
                          </div>
                        </td>
                        <td style={{ padding: '14px 16px', color: '#374151', fontFamily: 'monospace' }}>{user.username}</td>
                        <td style={{ padding: '14px 16px', color: '#374151', fontSize: '0.8125rem' }}>{user.email}</td>
                        <td style={{ padding: '14px 16px' }}>
                          <StatusBadge active={user.is_active} />
                        </td>
                        <td style={{ padding: '14px 16px' }}>
                          {isAdmin ? (
                            <span style={{ fontSize: '0.75rem', fontWeight: 700, color: TEAL }}>All Segments</span>
                          ) : segments.length === 0 ? (
                            <span style={{ fontSize: '0.75rem', color: '#9CA3AF', fontStyle: 'italic' }}>None</span>
                          ) : (
                            <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                              {segments.map(seg => (
                                <span key={seg} style={{ fontSize: '0.75rem', fontWeight: 600, color: BLUE, background: 'rgba(31,95,168,0.1)', padding: '2px 6px', borderRadius: 4 }}>
                                  {seg}
                                </span>
                              ))}
                            </div>
                          )}
                        </td>
                        <td style={{ padding: '14px 16px', fontWeight: 600, color: '#111827' }}>
                          {isAdmin ? 'All' : distCount}
                        </td>
                        <td style={{ padding: '14px 16px' }}>
                          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                            {(
                              [
                                { value: 'none', label: 'No Sync' },
                                { value: 'own', label: 'Sync Own Emails' },
                                { value: 'all', label: 'Sync All Emails' },
                              ] as const
                            ).map(opt => (
                              <label
                                key={opt.value}
                                style={{
                                  display: 'flex',
                                  alignItems: 'center',
                                  gap: 6,
                                  fontSize: '0.75rem',
                                  color: '#374151',
                                  cursor: busy ? 'not-allowed' : 'pointer',
                                  fontWeight: syncPerm === opt.value ? 700 : 500,
                                }}
                              >
                                <input
                                  type="radio"
                                  name={`outlook-sync-${user.id}`}
                                  checked={syncPerm === opt.value}
                                  disabled={busy}
                                  onChange={() => void handleOutlookSyncPermission(user, opt.value)}
                                />
                                {opt.label}
                              </label>
                            ))}
                          </div>
                        </td>
                        <td style={{ padding: '14px 20px', textAlign: 'right' }}>
                          <div style={{ display: 'inline-flex', gap: 8, alignItems: 'center', justifyContent: 'flex-end', position: 'relative' }}>
                            <button
                              type="button"
                              onClick={() => void openDistributors(user)}
                              title="Assign or add distributors"
                              style={{
                                padding: '6px 10px',
                                borderRadius: 6,
                                fontSize: '0.75rem',
                                fontWeight: 600,
                                background: 'white',
                                border: `1px solid ${BORDER}`,
                                color: BLUE,
                                cursor: 'pointer',
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: 4,
                              }}
                            >
                              <Building2 size={14} /> Distributors
                            </button>

                            <div style={{ position: 'relative' }}>
                              <button
                                type="button"
                                onClick={() =>
                                  setCredentialsMenuId(credentialsMenuId === user.id ? null : user.id)
                                }
                                title="Username & Password"
                                style={{
                                  padding: '6px 10px',
                                  borderRadius: 6,
                                  fontSize: '0.75rem',
                                  fontWeight: 600,
                                  background: credentialsMenuId === user.id ? 'rgba(31,95,168,0.08)' : 'white',
                                  border: `1px solid ${credentialsMenuId === user.id ? BLUE : BORDER}`,
                                  color: '#374151',
                                  cursor: 'pointer',
                                  display: 'inline-flex',
                                  alignItems: 'center',
                                }}
                              >
                                <KeyRound size={14} />
                              </button>
                              {credentialsMenuId === user.id && (
                                <div
                                  style={{
                                    position: 'absolute',
                                    right: 0,
                                    top: 'calc(100% + 4px)',
                                    minWidth: 160,
                                    background: 'white',
                                    border: `1px solid ${BORDER}`,
                                    borderRadius: 8,
                                    boxShadow: '0 8px 20px rgba(0,0,0,0.12)',
                                    zIndex: 20,
                                    overflow: 'hidden',
                                  }}
                                >
                                  <button
                                    type="button"
                                    onClick={() => {
                                      setCredentialsMenuId(null);
                                      openUsername(user);
                                    }}
                                    style={{
                                      width: '100%',
                                      textAlign: 'left',
                                      padding: '10px 14px',
                                      border: 'none',
                                      background: 'white',
                                      cursor: 'pointer',
                                      fontSize: '0.8125rem',
                                      fontWeight: 600,
                                      color: '#111827',
                                    }}
                                    onMouseEnter={e => {
                                      e.currentTarget.style.background = '#F8FAFC';
                                    }}
                                    onMouseLeave={e => {
                                      e.currentTarget.style.background = 'white';
                                    }}
                                  >
                                    Username
                                  </button>
                                  <button
                                    type="button"
                                    onClick={() => {
                                      setCredentialsMenuId(null);
                                      openEmail(user);
                                    }}
                                    style={{
                                      width: '100%',
                                      textAlign: 'left',
                                      padding: '10px 14px',
                                      border: 'none',
                                      borderTop: `1px solid ${BORDER}`,
                                      background: 'white',
                                      cursor: 'pointer',
                                      fontSize: '0.8125rem',
                                      fontWeight: 600,
                                      color: '#111827',
                                    }}
                                    onMouseEnter={e => {
                                      e.currentTarget.style.background = '#F8FAFC';
                                    }}
                                    onMouseLeave={e => {
                                      e.currentTarget.style.background = 'white';
                                    }}
                                  >
                                    Email
                                  </button>
                                  {(!isAdmin || isSuperAdminRole(userRole)) && (
                                    <button
                                      type="button"
                                      onClick={() => {
                                        setCredentialsMenuId(null);
                                        openPassword(user);
                                      }}
                                      style={{
                                        width: '100%',
                                        textAlign: 'left',
                                        padding: '10px 14px',
                                        border: 'none',
                                        borderTop: `1px solid ${BORDER}`,
                                        background: 'white',
                                        cursor: 'pointer',
                                        fontSize: '0.8125rem',
                                        fontWeight: 600,
                                        color: '#111827',
                                      }}
                                      onMouseEnter={e => {
                                        e.currentTarget.style.background = '#F8FAFC';
                                      }}
                                      onMouseLeave={e => {
                                        e.currentTarget.style.background = 'white';
                                      }}
                                    >
                                      Password
                                    </button>
                                  )}
                                </div>
                              )}
                            </div>

                            {!isAdmin && (
                              <button
                                type="button"
                                onClick={() => handleDeleteUser(user)}
                                title={`Delete ${user.full_name}`}
                                style={{
                                  padding: '6px 10px',
                                  borderRadius: 6,
                                  fontSize: '0.75rem',
                                  fontWeight: 600,
                                  background: 'rgba(220,38,38,0.08)',
                                  border: '1px solid rgba(220,38,38,0.2)',
                                  color: RED,
                                  cursor: 'pointer',
                                  display: 'inline-flex',
                                  alignItems: 'center',
                                }}
                              >
                                <Trash2 size={14} />
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* BULK UPLOAD EMPLOYEE MAPPING MODAL */}
      {bulkModalOpen && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
          <div style={{ background: 'white', borderRadius: 12, padding: 24, width: 620, maxWidth: '95vw', maxHeight: '90vh', overflowY: 'auto', boxShadow: '0 20px 25px -5px rgba(0,0,0,0.15)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
              <div>
                <h3 style={{ margin: 0, fontSize: '1.125rem', fontWeight: 700, color: '#111827' }}>Bulk Upload Employee Mapping</h3>
                <p style={{ margin: '2px 0 0', fontSize: '0.8125rem', color: '#6B7280' }}>
                  Upload Excel mapping file (Second Party, Owner, Segment) to auto-populate the user matrix.
                </p>
              </div>
              <button onClick={() => setBulkModalOpen(false)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#6B7280' }}><X size={20} /></button>
            </div>

            {bulkError && <StatusBanner message={bulkError} type="error" style={{ marginBottom: 16 }} />}

            {/* File Dropzone */}
            <div style={{ border: `2px dashed ${bulkFile ? BLUE : BORDER}`, borderRadius: 10, padding: 24, textAlign: 'center', background: bulkFile ? 'rgba(31,95,168,0.03)' : '#F9FAFB', marginBottom: 16 }}>
              <input
                type="file"
                accept=".xlsx,.xlsm"
                id="bulk-excel-input"
                style={{ display: 'none' }}
                onChange={e => {
                  const f = e.target.files?.[0];
                  if (f) handleFileChange(f);
                }}
              />
              <label htmlFor="bulk-excel-input" style={{ cursor: 'pointer', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8 }}>
                <Upload size={32} color={BLUE} />
                <span style={{ fontSize: '0.875rem', fontWeight: 600, color: '#374151' }}>
                  {bulkFile ? bulkFile.name : 'Click to select Excel file (.xlsx)'}
                </span>
                <span style={{ fontSize: '0.75rem', color: '#9CA3AF' }}>
                  Required columns: Second Party (Distributor), Owner (Employee), Segment
                </span>
              </label>
            </div>

            {/* Parsing State */}
            {bulkParsing && (
              <div style={{ padding: 16, textAlign: 'center', color: '#6B7280', fontSize: '0.875rem' }}>
                Parsing Excel file...
              </div>
            )}

            {/* Preview Summary */}
            {bulkPreview && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 14, marginBottom: 16 }}>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10 }}>
                  <div style={{ background: '#F3F4F6', padding: 12, borderRadius: 8, textAlign: 'center' }}>
                    <div style={{ fontSize: '1.25rem', fontWeight: 700, color: BLUE }}>{bulkPreview.total_rows}</div>
                    <div style={{ fontSize: '0.75rem', color: '#6B7280', fontWeight: 600 }}>Total Mappings</div>
                  </div>
                  <div style={{ background: '#F3F4F6', padding: 12, borderRadius: 8, textAlign: 'center' }}>
                    <div style={{ fontSize: '1.25rem', fontWeight: 700, color: TEAL }}>{bulkPreview.unique_owners}</div>
                    <div style={{ fontSize: '0.75rem', color: '#6B7280', fontWeight: 600 }}>Sales Owners</div>
                  </div>
                  <div style={{ background: '#F3F4F6', padding: 12, borderRadius: 8, textAlign: 'center' }}>
                    <div style={{ fontSize: '1.25rem', fontWeight: 700, color: '#059669' }}>{bulkPreview.new_users_count}</div>
                    <div style={{ fontSize: '0.75rem', color: '#6B7280', fontWeight: 600 }}>New Accounts To Create</div>
                  </div>
                </div>

                {(bulkPreview.admin_mapped_rows || 0) > 0 && (
                  <div style={{ fontSize: '0.8125rem', color: '#059669', fontWeight: 600 }}>
                    {bulkPreview.admin_mapped_rows} FYIP DC row(s) will map onto Admin (Deb).
                  </div>
                )}
                {bulkPreview.distributors_to_create?.length > 0 && (
                  <div style={{ fontSize: '0.8125rem', color: BLUE, background: 'rgba(31,95,168,0.06)', padding: '8px 12px', borderRadius: 8 }}>
                    <strong>{bulkPreview.distributors_to_create.length} distributor(s) not in Master yet</strong>
                    {' '}— they will be <strong>added automatically</strong> on import (Bajaj still skipped).
                    {' '}
                    {bulkPreview.distributors_to_create.slice(0, 8).join(', ')}
                    {bulkPreview.distributors_to_create.length > 8 ? '…' : ''}
                  </div>
                )}

                {/* Sample Records Table */}
                <div style={{ border: `1px solid ${BORDER}`, borderRadius: 8, overflow: 'hidden' }}>
                  <div style={{ background: '#F9FAFB', padding: '8px 12px', fontSize: '0.75rem', fontWeight: 700, color: '#374151', textTransform: 'uppercase' }}>
                    Parsed Sample Data (First {bulkPreview.preview_samples?.length} rows)
                  </div>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8125rem' }}>
                    <thead>
                      <tr style={{ background: '#F3F4F6', borderBottom: `1px solid ${BORDER}` }}>
                        <th style={{ padding: '6px 12px', fontWeight: 600 }}>Distributor (Second Party)</th>
                        <th style={{ padding: '6px 12px', fontWeight: 600 }}>Sales Owner</th>
                        <th style={{ padding: '6px 12px', fontWeight: 600 }}>Segment</th>
                      </tr>
                    </thead>
                    <tbody>
                      {bulkPreview.preview_samples?.map((s: any, idx: number) => (
                        <tr key={idx} style={{ borderBottom: `1px solid ${BORDER}` }}>
                          <td style={{ padding: '6px 12px', color: '#111827', fontWeight: 600 }}>{s.distributor}</td>
                          <td style={{ padding: '6px 12px', color: '#374151' }}>{s.owner}</td>
                          <td style={{ padding: '6px 12px', color: BLUE, fontWeight: 600 }}>{s.segment}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {/* Checkbox for Replace Existing */}
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: '0.875rem', color: '#374151', cursor: 'pointer', background: '#F9FAFB', padding: '10px 14px', borderRadius: 8, border: `1px solid ${BORDER}` }}>
                  <input
                    type="checkbox"
                    checked={bulkReplace}
                    onChange={e => setBulkReplace(e.target.checked)}
                    style={{ width: 16, height: 16, accentColor: BLUE }}
                  />
                  <span>
                    <strong>Replace all prior Sales Owners</strong> (keeps Super Admin + Admin).
                    Re-imports mappings; Bajaj skipped; FYIP DC → Admin (Deb); password for new sales logins = Sales@123.
                  </span>
                </label>
              </div>
            )}

            {/* Dialog Footer Actions */}
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 16 }}>
              <button
                type="button"
                onClick={() => setBulkModalOpen(false)}
                style={{ padding: '9px 16px', borderRadius: 8, border: `1px solid ${BORDER}`, background: 'white', cursor: 'pointer' }}
              >
                Cancel
              </button>

              <button
                type="button"
                disabled={!bulkPreview || bulkUploading}
                onClick={handleExecuteBulkImport}
                style={{
                  padding: '9px 20px',
                  borderRadius: 8,
                  border: 'none',
                  background: bulkPreview ? BLUE : '#9CA3AF',
                  color: 'white',
                  fontWeight: 600,
                  cursor: bulkPreview && !bulkUploading ? 'pointer' : 'not-allowed',
                }}
              >
                {bulkUploading ? 'Importing...' : 'Confirm Import'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* CREATE EMPLOYEE DIALOG */}
      {dialog === 'create' && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
          <div style={{ background: 'white', borderRadius: 12, padding: 24, width: 480, maxWidth: '90vw', boxShadow: '0 20px 25px -5px rgba(0,0,0,0.1)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
              <h3 style={{ margin: 0, fontSize: '1.125rem', fontWeight: 700 }}>Add New Employee</h3>
              <button onClick={() => setDialog(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#6B7280' }}><X size={20} /></button>
            </div>

            {formError && <StatusBanner message={formError} type="error" style={{ marginBottom: 16 }} />}

            <form onSubmit={handleSaveCreate} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              <div>
                <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: '#374151', marginBottom: 4 }}>Employee Name *</label>
                <input type="text" value={fullName} onChange={e => setFullName(e.target.value)} placeholder="e.g. Mr. Anup Pandey" style={inputStyle} required />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: '#374151', marginBottom: 4 }}>Username *</label>
                <input type="text" value={username} onChange={e => setUsername(e.target.value)} placeholder="e.g. anup" style={inputStyle} required />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: '#374151', marginBottom: 4 }}>Email Address</label>
                <input type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="e.g. anup@apcotex.com" style={inputStyle} />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: '#374151', marginBottom: 4 }}>Role</label>
                <select value={createRole} onChange={e => setCreateRole(e.target.value as 'admin' | 'user')} style={inputStyle}>
                  <option value="user">Sales Owner (User)</option>
                  <option value="admin">Admin (Full Access)</option>
                </select>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: '#374151', marginBottom: 4 }}>Initial Password *</label>
                <input type="password" value={password} onChange={e => setPassword(e.target.value)} style={inputStyle} required />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: '#374151', marginBottom: 4 }}>Confirm Password *</label>
                <input type="password" value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)} style={inputStyle} required />
              </div>

              {createRole === 'user' && (
                <div>
                  <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: '#374151', marginBottom: 6 }}>Assign Product Segments</label>
                  <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                    {ALL_SEGMENTS.map(seg => {
                      const checked = selectedSegments.includes(seg);
                      return (
                        <label key={seg} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: '0.8125rem', padding: '6px 10px', background: checked ? 'rgba(31,95,168,0.1)' : '#F3F4F6', borderRadius: 6, cursor: 'pointer', border: `1px solid ${checked ? BLUE : BORDER}` }}>
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={e => {
                              if (e.target.checked) setSelectedSegments([...selectedSegments, seg]);
                              else setSelectedSegments(selectedSegments.filter(s => s !== seg));
                            }}
                          />
                          {seg}
                        </label>
                      );
                    })}
                  </div>
                </div>
              )}

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 12 }}>
                <button type="button" onClick={() => setDialog(null)} style={{ padding: '9px 16px', borderRadius: 8, border: `1px solid ${BORDER}`, background: 'white', cursor: 'pointer' }}>Cancel</button>
                <button type="submit" disabled={busy} style={{ padding: '9px 16px', borderRadius: 8, border: 'none', background: BLUE, color: 'white', fontWeight: 600, cursor: busy ? 'not-allowed' : 'pointer' }}>
                  {busy ? 'Creating...' : 'Create Employee'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ASSIGN SEGMENTS DIALOG */}
      {dialog === 'segments' && target && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
          <div style={{ background: 'white', borderRadius: 12, padding: 24, width: 440, maxWidth: '90vw', boxShadow: '0 20px 25px -5px rgba(0,0,0,0.1)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
              <div>
                <h3 style={{ margin: 0, fontSize: '1.125rem', fontWeight: 700 }}>Edit Persona</h3>
                <p style={{ margin: '2px 0 0', fontSize: '0.8125rem', color: '#6B7280' }}>For {target.full_name} ({target.username})</p>
              </div>
              <button onClick={() => setDialog(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#6B7280' }}><X size={20} /></button>
            </div>

            {formError && <StatusBanner message={formError} type="error" style={{ marginBottom: 16 }} />}

            <form onSubmit={handleSaveSegments}>
              <div style={{ marginBottom: 16 }}>
                <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: '#374151', marginBottom: 4 }}>Email</label>
                <input type="email" value={email} onChange={e => setEmail(e.target.value)} style={inputStyle} required />
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 20 }}>
                <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: '#374151', marginBottom: 2 }}>Assign Segments</label>
                {ALL_SEGMENTS.map(seg => {
                  const checked = selectedSegments.includes(seg);
                  return (
                    <label key={seg} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 14px', borderRadius: 8, background: checked ? 'rgba(31,95,168,0.06)' : '#F9FAFB', border: `1px solid ${checked ? BLUE : BORDER}`, cursor: 'pointer' }}>
                      <span style={{ fontSize: '0.875rem', fontWeight: 600, color: checked ? BLUE : '#374151' }}>{seg}</span>
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={e => {
                          if (e.target.checked) setSelectedSegments([...selectedSegments, seg]);
                          else setSelectedSegments(selectedSegments.filter(s => s !== seg));
                        }}
                        style={{ width: 18, height: 18, accentColor: BLUE }}
                      />
                    </label>
                  );
                })}
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
                <button type="button" onClick={() => setDialog(null)} style={{ padding: '9px 16px', borderRadius: 8, border: `1px solid ${BORDER}`, background: 'white', cursor: 'pointer' }}>Cancel</button>
                <button type="submit" disabled={busy} style={{ padding: '9px 16px', borderRadius: 8, border: 'none', background: BLUE, color: 'white', fontWeight: 600, cursor: busy ? 'not-allowed' : 'pointer' }}>
                  {busy ? 'Saving...' : 'Save Permissions'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* CHANGE PASSWORD DIALOG */}
      {dialog === 'password' && target && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
          <div style={{ background: 'white', borderRadius: 12, padding: 24, width: 400, maxWidth: '90vw', boxShadow: '0 20px 25px -5px rgba(0,0,0,0.1)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
              <div>
                <h3 style={{ margin: 0, fontSize: '1.125rem', fontWeight: 700 }}>Reset Password</h3>
                <p style={{ margin: '2px 0 0', fontSize: '0.8125rem', color: '#6B7280' }}>For {target.full_name} ({target.username})</p>
              </div>
              <button onClick={() => setDialog(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#6B7280' }}><X size={20} /></button>
            </div>

            {formError && <StatusBanner message={formError} type="error" style={{ marginBottom: 16 }} />}

            <form onSubmit={handleSavePassword} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              <div>
                <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: '#374151', marginBottom: 4 }}>New Password *</label>
                <input type="password" value={password} onChange={e => setPassword(e.target.value)} style={inputStyle} required />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: '#374151', marginBottom: 4 }}>Confirm New Password *</label>
                <input type="password" value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)} style={inputStyle} required />
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 12 }}>
                <button type="button" onClick={() => setDialog(null)} style={{ padding: '9px 16px', borderRadius: 8, border: `1px solid ${BORDER}`, background: 'white', cursor: 'pointer' }}>Cancel</button>
                <button type="submit" disabled={busy} style={{ padding: '9px 16px', borderRadius: 8, border: 'none', background: BLUE, color: 'white', fontWeight: 600, cursor: busy ? 'not-allowed' : 'pointer' }}>
                  {busy ? 'Updating...' : 'Update Password'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* EDIT USERNAME DIALOG */}
      {dialog === 'username' && target && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
          <div style={{ background: 'white', borderRadius: 12, padding: 24, width: 400, maxWidth: '90vw', boxShadow: '0 20px 25px -5px rgba(0,0,0,0.1)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
              <div>
                <h3 style={{ margin: 0, fontSize: '1.125rem', fontWeight: 700 }}>Edit Username</h3>
                <p style={{ margin: '2px 0 0', fontSize: '0.8125rem', color: '#6B7280' }}>For {target.full_name}</p>
              </div>
              <button onClick={() => setDialog(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#6B7280' }}><X size={20} /></button>
            </div>

            {formError && <StatusBanner message={formError} type="error" style={{ marginBottom: 16 }} />}

            <form onSubmit={handleSaveUsername} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              <div>
                <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: '#374151', marginBottom: 4 }}>Username *</label>
                <input
                  type="text"
                  value={username}
                  onChange={e => setUsername(e.target.value)}
                  style={inputStyle}
                  required
                  minLength={3}
                />
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 12 }}>
                <button type="button" onClick={() => setDialog(null)} style={{ padding: '9px 16px', borderRadius: 8, border: `1px solid ${BORDER}`, background: 'white', cursor: 'pointer' }}>Cancel</button>
                <button type="submit" disabled={busy} style={{ padding: '9px 16px', borderRadius: 8, border: 'none', background: BLUE, color: 'white', fontWeight: 600, cursor: busy ? 'not-allowed' : 'pointer' }}>
                  {busy ? 'Saving...' : 'Save Username'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* EDIT EMAIL DIALOG */}
      {dialog === 'email' && target && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
          <div style={{ background: 'white', borderRadius: 12, padding: 24, width: 400, maxWidth: '90vw', boxShadow: '0 20px 25px -5px rgba(0,0,0,0.1)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
              <div>
                <h3 style={{ margin: 0, fontSize: '1.125rem', fontWeight: 700 }}>Edit Email</h3>
                <p style={{ margin: '2px 0 0', fontSize: '0.8125rem', color: '#6B7280' }}>For {target.full_name}</p>
              </div>
              <button type="button" onClick={() => setDialog(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#6B7280' }}>
                <X size={20} />
              </button>
            </div>

            {formError && <StatusBanner message={formError} type="error" style={{ marginBottom: 16 }} />}

            <form onSubmit={handleSaveEmail} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              <div>
                <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: '#374151', marginBottom: 4 }}>Email *</label>
                <input
                  type="email"
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  style={inputStyle}
                  required
                  placeholder="name@apcotex.com"
                />
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 12 }}>
                <button type="button" onClick={() => setDialog(null)} style={{ padding: '9px 16px', borderRadius: 8, border: `1px solid ${BORDER}`, background: 'white', cursor: 'pointer' }}>
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={busy}
                  style={{
                    padding: '9px 16px',
                    borderRadius: 8,
                    border: 'none',
                    background: BLUE,
                    color: 'white',
                    fontWeight: 600,
                    cursor: busy ? 'not-allowed' : 'pointer',
                  }}
                >
                  {busy ? 'Saving...' : 'Save Email'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* EDIT DISTRIBUTORS DIALOG (assign + add new) — segment-wise */}
      {dialog === 'distributors' && target && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
            padding: 16,
          }}
        >
          <div
            style={{
              background: 'white',
              borderRadius: 12,
              width: 560,
              maxWidth: '92vw',
              height: 'min(720px, 90vh)',
              maxHeight: '90vh',
              boxShadow: '0 20px 25px -5px rgba(0,0,0,0.1)',
              display: 'flex',
              flexDirection: 'column',
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: '20px 24px 12px',
                flexShrink: 0,
                borderBottom: `1px solid ${BORDER}`,
              }}
            >
              <div>
                <h3 style={{ margin: 0, fontSize: '1.125rem', fontWeight: 700 }}>Assign Distributors</h3>
                <p style={{ margin: '2px 0 0', fontSize: '0.8125rem', color: '#6B7280' }}>
                  {target.full_name} · Paper / Carpet / Construction / Rubber / Gloves
                </p>
              </div>
              <button type="button" onClick={() => setDialog(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#6B7280' }}>
                <X size={20} />
              </button>
            </div>

            <form
              onSubmit={handleSaveDistributors}
              style={{
                display: 'flex',
                flexDirection: 'column',
                flex: 1,
                minHeight: 0,
                overflow: 'hidden',
              }}
            >
              <div style={{ padding: '12px 24px 0', flexShrink: 0 }}>
                {formError && <StatusBanner message={formError} type="error" style={{ marginBottom: 12 }} />}

                <div
                  style={{
                    display: 'flex',
                    gap: 8,
                    marginBottom: 12,
                    padding: 12,
                    background: '#F8FAFC',
                    borderRadius: 8,
                    border: `1px solid ${BORDER}`,
                  }}
                >
                  <input
                    type="text"
                    value={newDistributorName}
                    onChange={e => setNewDistributorName(e.target.value)}
                    onKeyDown={e => {
                      if (e.key === 'Enter') {
                        e.preventDefault();
                        void handleAddDistributorInline();
                      }
                    }}
                    placeholder="New distributor company name…"
                    style={{ ...inputStyle, flex: 1 }}
                  />
                  <button
                    type="button"
                    onClick={() => void handleAddDistributorInline()}
                    disabled={addingDistributor || !newDistributorName.trim()}
                    style={{
                      padding: '0 14px',
                      borderRadius: 8,
                      border: 'none',
                      background: newDistributorName.trim() ? TEAL : '#9CA3AF',
                      color: 'white',
                      fontWeight: 600,
                      fontSize: '0.8125rem',
                      cursor: newDistributorName.trim() && !addingDistributor ? 'pointer' : 'not-allowed',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {addingDistributor ? 'Adding…' : '+ Add'}
                  </button>
                </div>

                <input
                  type="text"
                  value={distSearch}
                  onChange={e => setDistSearch(e.target.value)}
                  placeholder="Search distributors…"
                  style={{ ...inputStyle, marginBottom: 8 }}
                />
                <div style={{ fontSize: '0.75rem', color: '#6B7280', marginBottom: 8 }}>
                  {selectedDistributorIds.length} selected · scroll inside each segment to see all
                </div>
              </div>

              <div
                style={{
                  flex: 1,
                  minHeight: 0,
                  overflowY: 'auto',
                  overflowX: 'hidden',
                  overscrollBehavior: 'contain',
                  WebkitOverflowScrolling: 'touch',
                  padding: '0 24px 8px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 8,
                }}
              >
                {distributorsBySegment.map(group => {
                  const collapsed = collapsedDistSegments.includes(group.segment);
                  const selectedInGroup = group.items.filter(d =>
                    selectedDistributorIds.includes(d.id),
                  ).length;
                  if (distSearch.trim() && group.items.length === 0) return null;

                  return (
                    <div
                      key={group.segment}
                      style={{
                        border: `1px solid ${BORDER}`,
                        borderRadius: 8,
                        background: '#fff',
                        flexShrink: 0,
                        display: 'flex',
                        flexDirection: 'column',
                        maxHeight: collapsed ? undefined : 280,
                        overflow: 'hidden',
                      }}
                    >
                      <button
                        type="button"
                        onClick={() =>
                          setCollapsedDistSegments(prev =>
                            prev.includes(group.segment)
                              ? prev.filter(s => s !== group.segment)
                              : [...prev, group.segment],
                          )
                        }
                        style={{
                          width: '100%',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          gap: 8,
                          padding: '9px 12px',
                          border: 'none',
                          background: '#F1F5F9',
                          cursor: 'pointer',
                          textAlign: 'left',
                          flexShrink: 0,
                        }}
                      >
                        <span
                          style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: 8,
                            fontSize: '0.8125rem',
                            fontWeight: 700,
                            color: '#0F172A',
                          }}
                        >
                          {collapsed ? (
                            <ChevronRight size={16} color={BLUE} />
                          ) : (
                            <ChevronDown size={16} color={BLUE} />
                          )}
                          {group.segment}
                        </span>
                        <span style={{ fontSize: '0.6875rem', color: '#64748B', fontWeight: 600 }}>
                          {selectedInGroup}/{group.items.length}
                        </span>
                      </button>

                      {!collapsed && (
                        <div
                          style={{
                            padding: '4px 6px 8px',
                            display: 'flex',
                            flexDirection: 'column',
                            gap: 2,
                            borderLeft: `3px solid ${TEAL}`,
                            marginLeft: 14,
                            overflowY: 'auto',
                            overflowX: 'hidden',
                            overscrollBehavior: 'contain',
                            WebkitOverflowScrolling: 'touch',
                            minHeight: 0,
                            flex: 1,
                          }}
                        >
                          {group.items.length === 0 ? (
                            <div
                              style={{
                                padding: '10px 12px',
                                color: '#94A3B8',
                                fontSize: '0.75rem',
                                fontStyle: 'italic',
                              }}
                            >
                              No distributors mapped to this segment yet
                            </div>
                          ) : (
                            group.items.map(d => {
                              const checked = selectedDistributorIds.includes(d.id);
                              return (
                                <label
                                  key={d.id}
                                  style={{
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: 10,
                                    padding: '7px 10px',
                                    borderRadius: 6,
                                    background: checked ? 'rgba(31,95,168,0.08)' : 'transparent',
                                    cursor: 'pointer',
                                    fontSize: '0.8125rem',
                                    color: '#111827',
                                    flexShrink: 0,
                                  }}
                                >
                                  <input
                                    type="checkbox"
                                    checked={checked}
                                    onChange={e => {
                                      if (e.target.checked) {
                                        setSelectedDistributorIds(prev => [...prev, d.id]);
                                      } else {
                                        setSelectedDistributorIds(prev =>
                                          prev.filter(id => id !== d.id),
                                        );
                                      }
                                    }}
                                    style={{ width: 15, height: 15, accentColor: BLUE }}
                                  />
                                  {d.name}
                                </label>
                              );
                            })
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
                {allDistributors.length === 0 && (
                  <div style={{ padding: 16, color: '#94A3B8', fontSize: '0.8125rem' }}>
                    No distributors yet. Use + Add above to create one.
                  </div>
                )}
              </div>

              <div
                style={{
                  display: 'flex',
                  justifyContent: 'flex-end',
                  gap: 10,
                  padding: '12px 24px 20px',
                  borderTop: `1px solid ${BORDER}`,
                  flexShrink: 0,
                  background: 'white',
                }}
              >
                <button type="button" onClick={() => setDialog(null)} style={{ padding: '9px 16px', borderRadius: 8, border: `1px solid ${BORDER}`, background: 'white', cursor: 'pointer' }}>
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={busy}
                  style={{
                    padding: '9px 16px',
                    borderRadius: 8,
                    border: 'none',
                    background: BLUE,
                    color: 'white',
                    fontWeight: 600,
                    cursor: busy ? 'not-allowed' : 'pointer',
                  }}
                >
                  {busy ? 'Saving...' : 'Save Assignment'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* RENAME DISTRIBUTORS DIALOG (matrix spelling fixes) */}
      {dialog === 'renameDistributors' && target && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
          <div style={{ background: 'white', borderRadius: 12, padding: 24, width: 480, maxWidth: '92vw', maxHeight: '85vh', overflow: 'auto', boxShadow: '0 20px 25px -5px rgba(0,0,0,0.1)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
              <div>
                <h3 style={{ margin: 0, fontSize: '1.125rem', fontWeight: 700 }}>Edit Distributor Names</h3>
                <p style={{ margin: '2px 0 0', fontSize: '0.8125rem', color: '#6B7280' }}>
                  {target.full_name} · fix spelling mistakes (assignment is under Employee Accounts)
                </p>
              </div>
              <button type="button" onClick={() => setDialog(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#6B7280' }}>
                <X size={20} />
              </button>
            </div>

            {formError && <StatusBanner message={formError} type="error" style={{ marginBottom: 16 }} />}

            <form onSubmit={handleSaveRenamedDistributors} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {renameDistributorRows.map((row, idx) => (
                <div key={row.id}>
                  <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, color: '#6B7280', marginBottom: 4 }}>
                    Distributor #{idx + 1}
                  </label>
                  <input
                    type="text"
                    value={row.name}
                    onChange={e => {
                      const value = e.target.value;
                      setRenameDistributorRows(prev =>
                        prev.map(r => (r.id === row.id ? { ...r, name: value } : r)),
                      );
                    }}
                    style={inputStyle}
                    required
                  />
                </div>
              ))}

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 8 }}>
                <button type="button" onClick={() => setDialog(null)} style={{ padding: '9px 16px', borderRadius: 8, border: `1px solid ${BORDER}`, background: 'white', cursor: 'pointer' }}>
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={busy}
                  style={{
                    padding: '9px 16px',
                    borderRadius: 8,
                    border: 'none',
                    background: BLUE,
                    color: 'white',
                    fontWeight: 600,
                    cursor: busy ? 'not-allowed' : 'pointer',
                  }}
                >
                  {busy ? 'Saving...' : 'Save Names'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* REMOVE SEGMENT ACCESS CONFIRMATION */}
      {untickConfirm && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1100,
          }}
        >
          <div
            style={{
              background: 'white',
              borderRadius: 12,
              padding: 24,
              width: 460,
              maxWidth: '92vw',
              boxShadow: '0 20px 25px -5px rgba(0,0,0,0.1)',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 14 }}>
              <h3 style={{ margin: 0, fontSize: '1.125rem', fontWeight: 700, color: '#0F172A' }}>
                Remove Segment Access
              </h3>
              <button
                type="button"
                onClick={() => setUntickConfirm(null)}
                disabled={untickConfirming}
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#6B7280' }}
              >
                <X size={20} />
              </button>
            </div>

            <p style={{ margin: '0 0 16px', fontSize: '0.875rem', color: '#374151', lineHeight: 1.55 }}>
              You are removing <strong>{untickConfirm.segment}</strong> access for{' '}
              <strong>{untickConfirm.userName}</strong>.
              <br />
              <br />
              Should this employee retain visibility of historical data for this segment?
            </p>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 20 }}>
              <label
                style={{
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: 10,
                  padding: '10px 12px',
                  borderRadius: 8,
                  border: `1px solid ${retainHistoryChoice === 'yes' ? BLUE : BORDER}`,
                  background: retainHistoryChoice === 'yes' ? 'rgba(31,95,168,0.06)' : '#F9FAFB',
                  cursor: 'pointer',
                }}
              >
                <input
                  type="radio"
                  name="retain-history"
                  checked={retainHistoryChoice === 'yes'}
                  onChange={() => setRetainHistoryChoice('yes')}
                  style={{ marginTop: 3, accentColor: BLUE }}
                />
                <span style={{ fontSize: '0.8125rem', color: '#1E293B' }}>
                  <strong>Yes</strong> — Retain historical visibility
                </span>
              </label>
              <label
                style={{
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: 10,
                  padding: '10px 12px',
                  borderRadius: 8,
                  border: `1px solid ${retainHistoryChoice === 'no' ? BLUE : BORDER}`,
                  background: retainHistoryChoice === 'no' ? 'rgba(31,95,168,0.06)' : '#F9FAFB',
                  cursor: 'pointer',
                }}
              >
                <input
                  type="radio"
                  name="retain-history"
                  checked={retainHistoryChoice === 'no'}
                  onChange={() => setRetainHistoryChoice('no')}
                  style={{ marginTop: 3, accentColor: BLUE }}
                />
                <span style={{ fontSize: '0.8125rem', color: '#1E293B' }}>
                  <strong>No</strong> — Remove historical visibility completely
                </span>
              </label>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
              <button
                type="button"
                onClick={() => setUntickConfirm(null)}
                disabled={untickConfirming}
                style={{
                  padding: '9px 16px',
                  borderRadius: 8,
                  border: `1px solid ${BORDER}`,
                  background: 'white',
                  cursor: untickConfirming ? 'not-allowed' : 'pointer',
                }}
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => void confirmUntickSegment()}
                disabled={untickConfirming}
                style={{
                  padding: '9px 16px',
                  borderRadius: 8,
                  border: 'none',
                  background: RED,
                  color: 'white',
                  fontWeight: 600,
                  cursor: untickConfirming ? 'not-allowed' : 'pointer',
                }}
              >
                {untickConfirming ? 'Confirming…' : 'Confirm'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
