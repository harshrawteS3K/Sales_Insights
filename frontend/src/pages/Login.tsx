import { useState } from 'react';
import APCOTEX_LOGO from '../assets/images/apcotexindustrieslogo.png';
import { BLUE, TEAL, RED, BORDER } from '../constants/theme';
import { AuthService } from '../services/auth.service';
import { ApiError } from '../api';
import type { UserRole } from '../types';

const TEXT = '#1F2937';

const CONNECTION_ERROR =
  'Unable to connect to the server. Please verify the server is running and reachable.';

/** Map login failures: auth vs network/CORS — never mislabel connectivity as bad password. */
function resolveLoginError(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 401) {
      return err.message?.trim() || 'Invalid username or password';
    }
    if (err.status === 0 || err.code === 'NETWORK_ERROR') {
      return err.message?.trim() || CONNECTION_ERROR;
    }
    return err.message?.trim() || CONNECTION_ERROR;
  }
  if (err instanceof TypeError || err instanceof DOMException) {
    return CONNECTION_ERROR;
  }
  if (err instanceof Error) {
    const msg = err.message.toLowerCase();
    if (
      msg.includes('failed to fetch') ||
      msg.includes('network') ||
      msg.includes('load failed') ||
      msg.includes('aborted') ||
      msg.includes('timeout')
    ) {
      return CONNECTION_ERROR;
    }
  }
  return CONNECTION_ERROR;
}

export function Login({
  onLogin,
}: {
  onLogin: (role: UserRole, name: string, title: string) => void;
}) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    if (!username || !password) {
      setError('Please Enter the Credentials');
      return;
    }
    setLoading(true);
    try {
      const user = await AuthService.login(username.trim(), password);
      onLogin(user.role, user.name, user.title);
    } catch (err) {
      setError(resolveLoginError(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'linear-gradient(135deg, #1F5FA8 0%, #1FB7B5 100%)',
        fontFamily: "'Inter', system-ui, sans-serif",
      }}
    >
      <div
        style={{
          background: 'white',
          borderRadius: 12,
          boxShadow: '0 8px 24px rgba(31,95,168,0.15)',
          padding: '48px 40px',
          width: '100%',
          maxWidth: 420,
        }}
      >
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <img
            src={APCOTEX_LOGO}
            alt="Apcotex"
            style={{ height: 70, width: 'auto', marginBottom: 20, display: 'block', marginLeft: 'auto', marginRight: 'auto' }}
          />
          <h1 style={{ fontSize: '1.5rem', fontWeight: 700, marginBottom: 8 }}>
            <span style={{ color: BLUE }}>Sales</span>{' '}
            <span style={{ color: RED }}>Insights</span>{' '}
            <span style={{ color: TEAL }}>Dashboard</span>
          </h1>
          <p style={{ fontSize: '0.875rem', color: '#6B7280' }}>Sign in to continue</p>
        </div>

        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: 20 }}>
            <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: TEXT, marginBottom: 8 }}>
              Username
            </label>
            <input
              type="text"
              value={username}
              onChange={e => setUsername(e.target.value)}
              placeholder="Enter username"
              autoComplete="username"
              disabled={loading}
              style={{ width: '100%', padding: '10px 14px', fontSize: '0.875rem', border: `1px solid ${BORDER}`, borderRadius: 8, outline: 'none', transition: 'border-color 0.15s' }}
              onFocus={e => { e.currentTarget.style.borderColor = TEAL; }}
              onBlur={e => { e.currentTarget.style.borderColor = BORDER; }}
            />
          </div>

          <div style={{ marginBottom: 24 }}>
            <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: TEXT, marginBottom: 8 }}>
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="Enter password"
              autoComplete="current-password"
              disabled={loading}
              style={{ width: '100%', padding: '10px 14px', fontSize: '0.875rem', border: `1px solid ${BORDER}`, borderRadius: 8, outline: 'none', transition: 'border-color 0.15s' }}
              onFocus={e => { e.currentTarget.style.borderColor = TEAL; }}
              onBlur={e => { e.currentTarget.style.borderColor = BORDER; }}
            />
          </div>

          {error && (
            <div style={{ padding: '10px 14px', background: 'rgba(217,58,47,0.08)', borderRadius: 6, marginBottom: 20 }}>
              <p style={{ fontSize: '0.8125rem', color: RED, margin: 0 }}>{error}</p>
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            style={{
              width: '100%',
              padding: '12px',
              fontSize: '0.875rem',
              fontWeight: 600,
              color: 'white',
              background: loading ? '#9CA3AF' : TEAL,
              border: 'none',
              borderRadius: 8,
              cursor: loading ? 'not-allowed' : 'pointer',
              transition: 'background 0.15s',
            }}
            onMouseEnter={e => { if (!loading) e.currentTarget.style.background = '#1ba09e'; }}
            onMouseLeave={e => { if (!loading) e.currentTarget.style.background = TEAL; }}
          >
            {loading ? 'Signing In…' : 'Sign In'}
          </button>
        </form>
      </div>
    </div>
  );
}
