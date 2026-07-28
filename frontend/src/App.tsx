import { useState, useEffect } from 'react';
import { RouterProvider } from 'react-router';
import { Login } from './pages/Login';
import { createAppRouter } from './routes';
import { clearSession, getSession, saveSession } from './api';

export default function App() {
  const existing = getSession();
  const [isAuthenticated, setIsAuthenticated] = useState(Boolean(existing));
  const [userRole, setUserRole] = useState<'admin' | 'user' | null>(existing?.role ?? null);
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

  const handleLogin = (role: 'admin' | 'user', name: string, title: string) => {
    saveSession({ role, name, title });
    setIsAuthenticated(true);
    setUserRole(role);
    setUserName(name);
    setUserTitle(title);
  };

  const handleLogout = () => {
    clearSession();
    setIsAuthenticated(false);
    setUserRole(null);
    setUserName('');
    setUserTitle('');
  };

  if (!isAuthenticated) {
    return <Login onLogin={handleLogin} />;
  }

  const router = createAppRouter(userRole, userName, userTitle, handleLogout);

  return <RouterProvider router={router} />;
}
