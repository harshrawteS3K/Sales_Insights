import { useState, useEffect } from 'react';
import { RouterProvider } from 'react-router';
import { Login } from './pages/Login';
import { createAppRouter } from './routes';
import { clearSession, getSession, saveSession } from './api';
import { AuditTrailService } from './services/auditTrail.service';
import type { LoginResult } from './services/auth.service';
import type { OutlookSyncPermission, UserRole } from './types';

function logoutActionLabel(role: UserRole): string {
  if (role === 'super_admin') return 'Super Admin Logout';
  if (role === 'admin') return 'Admin Logout';
  return 'User Logout';
}

function defaultSyncPermission(role: UserRole | null | undefined): OutlookSyncPermission {
  if (role === 'admin' || role === 'super_admin') return 'all';
  return 'own';
}

export default function App() {
  const existing = getSession();
  const [isAuthenticated, setIsAuthenticated] = useState(Boolean(existing));
  const [userRole, setUserRole] = useState<UserRole | null>(existing?.role ?? null);
  const [userName, setUserName] = useState(existing?.name ?? '');
  const [userTitle, setUserTitle] = useState(existing?.title ?? '');
  const [outlookSyncPermission, setOutlookSyncPermission] = useState<OutlookSyncPermission>(
    existing?.outlook_sync_permission ?? defaultSyncPermission(existing?.role),
  );

  useEffect(() => {
    const session = getSession();
    if (session) {
      setIsAuthenticated(true);
      setUserRole(session.role);
      setUserName(session.name);
      setUserTitle(session.title);
      setOutlookSyncPermission(
        session.outlook_sync_permission ?? defaultSyncPermission(session.role),
      );
    }
  }, []);

  const handleLogin = (user: LoginResult) => {
    const syncPerm = user.outlook_sync_permission ?? defaultSyncPermission(user.role);
    saveSession({
      role: user.role,
      name: user.name,
      title: user.title,
      username: user.username,
      user_id: user.user_id,
      email: user.email ?? null,
      segments: user.segments,
      distributor_ids: user.distributor_ids ?? [],
      access_mode: user.access_mode ?? 'segment',
      outlook_sync_permission: syncPerm,
    });
    setIsAuthenticated(true);
    setUserRole(user.role);
    setUserName(user.name);
    setUserTitle(user.title);
    setOutlookSyncPermission(syncPerm);
  };

  const handleLogout = () => {
    const session = getSession();
    const finish = () => {
      clearSession();
      setIsAuthenticated(false);
      setUserRole(null);
      setUserName('');
      setUserTitle('');
      setOutlookSyncPermission('own');
    };
    if (session) {
      void AuditTrailService.recordEvent({
        action: logoutActionLabel(session.role),
        module: 'Authentication',
        description: `${session.name} signed out`,
        status: 'Info',
        entity_type: 'auth',
      }).finally(finish);
    } else {
      finish();
    }
  };

  if (!isAuthenticated) {
    return <Login onLogin={handleLogin} />;
  }

  const router = createAppRouter(
    userRole,
    userName,
    userTitle,
    handleLogout,
    outlookSyncPermission,
  );

  return <RouterProvider router={router} />;
}
