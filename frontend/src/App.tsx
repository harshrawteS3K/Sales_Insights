import { useState, useEffect } from 'react';
import { RouterProvider } from 'react-router';
import { Login } from './pages/Login';
import { createAppRouter } from './routes';
import { clearSession, getSession, saveSession } from './api';
import { AuditTrailService } from './services/auditTrail.service';
import type { UserRole } from './types';

function logoutActionLabel(role: UserRole): string {
  if (role === 'super_admin') return 'Super Admin Logout';
  if (role === 'admin') return 'Admin Logout';
  return 'User Logout';
}

export default function App() {
  const existing = getSession();
  const [isAuthenticated, setIsAuthenticated] = useState(Boolean(existing));
  const [userRole, setUserRole] = useState<UserRole | null>(existing?.role ?? null);
  const [userName, setUserName] = useState(existing?.name ?? '');
  const [userTitle, setUserTitle] = useState(existing?.title ?? '');

  useEffect(() => {
    const session = getSession();
    if (session) {
      setIsAuthenticated(true);
      setUserRole(session.role);
      setUserName(session.name);
      setUserTitle(session.title);
    }
  }, []);

  const handleLogin = (role: UserRole, name: string, title: string) => {
    saveSession({ role, name, title });
    setIsAuthenticated(true);
    setUserRole(role);
    setUserName(name);
    setUserTitle(title);
    // Login audit is recorded server-side by POST /auth/login
  };

  const handleLogout = () => {
    const session = getSession();
    const finish = () => {
      clearSession();
      setIsAuthenticated(false);
      setUserRole(null);
      setUserName('');
      setUserTitle('');
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

  const router = createAppRouter(userRole, userName, userTitle, handleLogout);

  return <RouterProvider router={router} />;
}
