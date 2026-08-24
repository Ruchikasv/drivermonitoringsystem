import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import AppLayout from './components/layout/AppLayout';

import DashboardPage from './pages/DashboardPage';
import DriversPage from './pages/DriversPage';
import DriverDetailPage from './pages/DriverDetailPage';
import VehicleManagementPage from './pages/VehicleManagementPage';
import OwnerMonitoringPage from './pages/owner/OwnerMonitoringPage';
import OwnerIncidentsPage from './pages/owner/OwnerIncidentsPage';
import TripsPage from './pages/TripsPage';
import AnalyticsPage from './pages/AnalyticsPage';
import SettingsPage from './pages/SettingsPage';
import NotFoundPage from './pages/NotFoundPage';

// Driver Cab Portal Pages (Isolated clean layout, no sidebar)
import DriverPortalPage from './pages/driver/DriverPortalPage';
import DriverRegisterPage from './pages/driver/DriverRegisterPage';
import DriverAuthPage from './pages/driver/DriverAuthPage';
import DriverMonitoringPage from './pages/driver/DriverMonitoringPage';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Driver Cab Portal Routes (Independent layout) */}
        <Route path="/driver" element={<DriverPortalPage />} />
        <Route path="/driver/register" element={<DriverRegisterPage />} />
        <Route path="/driver/auth" element={<DriverAuthPage />} />
        <Route path="/driver/monitoring" element={<DriverMonitoringPage />} />

        {/* Owner / Fleet Manager Portal Routes (With Sidebar AppLayout) */}
        <Route path="/" element={<AppLayout />}>
          <Route index element={<DashboardPage />} />
          <Route path="drivers" element={<DriversPage />} />
          <Route path="drivers/:id" element={<DriverDetailPage />} />
          <Route path="vehicles" element={<VehicleManagementPage />} />
          <Route path="live-monitoring" element={<OwnerMonitoringPage />} />
          <Route path="incidents" element={<OwnerIncidentsPage />} />
          <Route path="alerts" element={<OwnerIncidentsPage />} />
          <Route path="trips" element={<TripsPage />} />
          <Route path="analytics" element={<AnalyticsPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="404" element={<NotFoundPage />} />
          <Route path="*" element={<Navigate to="/404" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

