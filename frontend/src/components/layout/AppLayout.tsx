import { Outlet, useOutletContext } from 'react-router';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';
import type { LayoutContext } from '../../types';
import type { UserRole } from '../../types';

interface AppLayoutProps {
  userRole: UserRole | null;
  userName: string;
  userTitle: string;
  onLogout: () => void;
}

export function AppLayout({ userRole, userName, userTitle, onLogout }: AppLayoutProps) {
  return (
    <div
      className="flex h-screen overflow-hidden"
      style={{ fontFamily: "'Inter', system-ui, sans-serif", background: '#F7FAFC' }}
    >
      <Sidebar userName={userName} userTitle={userTitle} userRole={userRole} onLogout={onLogout} />
      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
        <TopBar userName={userName} />
        <main className="flex-1 overflow-y-auto" style={{ background: '#F7FAFC', position: 'relative' }}>
          <div style={{ minHeight: '100%', display: 'flex', flexDirection: 'column' }}>
            <div style={{ flex: 1 }}>
              <Outlet context={{ userRole, userName, userTitle } satisfies LayoutContext} />
            </div>
            <footer
              style={{
                background: '#2D2D2D',
                borderTop: '1px solid #3D3D3D',
                marginTop: 'auto',
              }}
            >
              {/* Products & Applications Section */}
              <div style={{ padding: '64px 80px 56px', maxWidth: 1400, margin: '0 auto' }}>
                <h3 style={{
                  fontSize: '1.5rem',
                  fontWeight: 500,
                  color: '#F3F4F6',
                  marginBottom: 48,
                  letterSpacing: '0.02em',
                  textAlign: 'left'
                }}>
                  Products & Applications
                </h3>

                <div className="grid grid-cols-3 gap-20" style={{ marginBottom: 80 }}>
                  {/* Column 1: Synthetic Rubber */}
                  <div>
                    <h4 style={{
                      fontSize: '1.125rem',
                      fontWeight: 500,
                      color: '#F3F4F6',
                      marginBottom: 24,
                      letterSpacing: '0.01em'
                    }}>
                      Synthetic Rubber
                    </h4>
                    <ul style={{
                      listStyle: 'none',
                      padding: 0,
                      margin: 0,
                      fontSize: '0.9375rem',
                      color: '#B0B0B0',
                      lineHeight: 2.2,
                      fontWeight: 400
                    }}>
                      <li>NBR</li>
                      <li>NBR - PVC Polyblend</li>
                      <li>HSR</li>
                      <li>PNBR</li>
                    </ul>
                  </div>

                  {/* Column 2: Synthetic Latex */}
                  <div>
                    <h4 style={{
                      fontSize: '1.125rem',
                      fontWeight: 500,
                      color: '#F3F4F6',
                      marginBottom: 24,
                      letterSpacing: '0.01em'
                    }}>
                      Synthetic Latex
                    </h4>
                    <div className="grid grid-cols-2 gap-8">
                      <ul style={{
                        listStyle: 'none',
                        padding: 0,
                        margin: 0,
                        fontSize: '0.9375rem',
                        color: '#B0B0B0',
                        lineHeight: 2.2,
                        fontWeight: 400
                      }}>
                        <li>SB Latex</li>
                        <li>Pure Acrylic Latex</li>
                        <li>XSB Latex</li>
                        <li>Styrene Acrylic Latex</li>
                      </ul>
                      <ul style={{
                        listStyle: 'none',
                        padding: 0,
                        margin: 0,
                        fontSize: '0.9375rem',
                        color: '#B0B0B0',
                        lineHeight: 2.2,
                        fontWeight: 400
                      }}>
                        <li>Vinyl Pyridine Latex</li>
                        <li>XNB Latex</li>
                        <li>NBR Latex</li>
                      </ul>
                    </div>
                  </div>

                  {/* Column 3: Applications / Industries */}
                  <div>
                    <h4 style={{
                      fontSize: '1.125rem',
                      fontWeight: 500,
                      color: '#F3F4F6',
                      marginBottom: 24,
                      letterSpacing: '0.01em'
                    }}>
                      Applications / Industries
                    </h4>
                    <div className="grid grid-cols-2 gap-8">
                      <ul style={{
                        listStyle: 'none',
                        padding: 0,
                        margin: 0,
                        fontSize: '0.9375rem',
                        color: '#B0B0B0',
                        lineHeight: 2.2,
                        fontWeight: 400
                      }}>
                        <li>Paper and Paperboard</li>
                        <li>Carpet</li>
                        <li>Construction and waterproofing</li>
                        <li>Textiles</li>
                      </ul>
                      <ul style={{
                        listStyle: 'none',
                        padding: 0,
                        margin: 0,
                        fontSize: '0.9375rem',
                        color: '#B0B0B0',
                        lineHeight: 2.2,
                        fontWeight: 400
                      }}>
                        <li>Tyre cord</li>
                        <li>Gloves</li>
                        <li>Specialty</li>
                      </ul>
                    </div>
                  </div>
                </div>

                {/* Bottom Footer Row */}
                <div style={{
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  gap: 28
                }}>
                  {/* Links */}
                  <div style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 16,
                    fontSize: '0.9375rem'
                  }}>
                    <a
                      href="#"
                      style={{
                        color: '#B0B0B0',
                        textDecoration: 'none',
                        transition: 'color 0.2s',
                        fontWeight: 400
                      }}
                      onMouseEnter={(e) => e.currentTarget.style.color = '#F3F4F6'}
                      onMouseLeave={(e) => e.currentTarget.style.color = '#B0B0B0'}
                    >
                      Terms & Conditions
                    </a>
                    <span style={{ color: '#5A5A5A' }}>|</span>
                    <a
                      href="#"
                      style={{
                        color: '#B0B0B0',
                        textDecoration: 'none',
                        transition: 'color 0.2s',
                        fontWeight: 400
                      }}
                      onMouseEnter={(e) => e.currentTarget.style.color = '#F3F4F6'}
                      onMouseLeave={(e) => e.currentTarget.style.color = '#B0B0B0'}
                    >
                      Privacy Policy
                    </a>
                  </div>

                  {/* LinkedIn Icon with Divider Lines */}
                  <div style={{
                    display: 'flex',
                    alignItems: 'center',
                    width: '100%',
                    maxWidth: 1200,
                    gap: 0
                  }}>
                    <div style={{ flex: 1, height: 1, background: '#4A4A4A' }} />
                    <a
                      href="https://linkedin.com"
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{
                        margin: '0 40px',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        width: 40,
                        height: 40,
                        borderRadius: '50%',
                        background: '#F3F4F6',
                        transition: 'background 0.2s'
                      }}
                      onMouseEnter={(e) => e.currentTarget.style.background = '#FFFFFF'}
                      onMouseLeave={(e) => e.currentTarget.style.background = '#F3F4F6'}
                    >
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="#2D2D2D">
                        <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/>
                      </svg>
                    </a>
                    <div style={{ flex: 1, height: 1, background: '#4A4A4A' }} />
                  </div>

                  {/* Copyright */}
                  <p style={{
                    margin: 0,
                    fontSize: '0.9375rem',
                    color: '#808080',
                    letterSpacing: '0.02em',
                    fontWeight: 400
                  }}>
                    Apcotex © Copyright 2026. All Rights Reserved. Designed & Developed by S3K Technologies
                  </p>
                </div>
              </div>
            </footer>
          </div>
        </main>
      </div>
    </div>
  );
}

/** @deprecated Use the hook from src/hooks/useLayoutContext.ts instead */
export function useLayoutContext() {
  return useOutletContext<LayoutContext>();
}
