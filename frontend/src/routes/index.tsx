import React from 'react';
import { createBrowserRouter } from 'react-router';
import { AppLayout } from '../components/layout/AppLayout';
import { SalesDashboard } from '../pages/Dashboard/SalesDashboard';
import { EmailsModule } from '../pages/Outlook/EmailsModule';
import { ConsolidatedData } from '../pages/ConsolidatedData/ConsolidatedData';
import { Visualizations } from '../pages/Visualizations/Visualizations';
import { AuditTrail } from '../pages/AuditTrail/AuditTrail';
import { UserManagement } from '../pages/UserManagement/UserManagement';
import { ExistingReports } from '../pages/Reports/ExistingReports';
import { MarketResearchDashboard } from '../pages/MarketResearch/MarketResearchDashboard';
import { MarketResearchCompanion } from '../pages/MarketResearch/MarketResearchCompanion';
import { DistributorManagement } from '../pages/DistributorManagement/DistributorManagement';
import { HeaderDictionaryPage } from '../pages/Admin/HeaderDictionaryPage';
import { PlaceholderPage } from '../pages/Settings/PlaceholderPage';
import { SettingsPage } from '../pages/Settings/SettingsPage';
import type { OutlookSyncPermission, UserRole } from '../types';

/**
 * Creates the browser router with app layout shell and children pages.
 * Passes the logged-in user context to the layout.
 */
export const createAppRouter = (
  userRole: UserRole | null,
  userName: string,
  userTitle: string,
  onLogout: () => void,
  outlookSyncPermission: OutlookSyncPermission = 'own',
) => {
  return createBrowserRouter([
    {
      path: '/',
      element: (
        <AppLayout
          userRole={userRole}
          userName={userName}
          userTitle={userTitle}
          onLogout={onLogout}
          outlookSyncPermission={outlookSyncPermission}
        />
      ),
      children: [
        { index: true, Component: SalesDashboard },
        ...(outlookSyncPermission === 'none'
          ? []
          : [{ path: 'emails', Component: EmailsModule }]),
        { path: 'consolidated-data', Component: ConsolidatedData },
        { path: 'visualizations', Component: Visualizations },
        { path: 'distributors', Component: DistributorManagement },
        { path: 'audit-trail', Component: AuditTrail },
        { path: 'user-management', Component: UserManagement },
        { path: 'admin/header-dictionary', Component: HeaderDictionaryPage },
        { path: 'existing-reports', Component: ExistingReports },
        { path: 'market-research-dashboard', Component: MarketResearchDashboard },
        { path: 'market-research-companion', Component: MarketResearchCompanion },
        { path: 'settings', Component: SettingsPage },
        { path: 'experiments', Component: PlaceholderPage },
        { path: 'products', Component: PlaceholderPage },
      ],
    },
  ]);
};
