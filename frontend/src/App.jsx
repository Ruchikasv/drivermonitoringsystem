import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import { ProtectedRoute } from './components/ProtectedRoute';
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

// Owner Authentication Pages
import { OwnerLoginPage } from './pages/owner/OwnerLoginPage';
import { OwnerRegisterPage } from './pages/owner/OwnerRegisterPage';

// Driver Cab Portal Pages (Isolated clean layout, no sidebar)
import DriverPortalPage from './pages/driver/DriverPortalPage';
import DriverRegisterPage from './pages/driver/DriverRegisterPage';
import DriverAuthPage from './pages/driver/DriverAuthPage';
import DriverMonitoringPage from './pages/driver/DriverMonitoringPage';

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          {/* Owner Authentication Routes */}
          <Route path="/owner/login" element={<OwnerLoginPage />} />
          <Route path="/owner/register" element={<OwnerRegisterPage />} />

          {/* Driver Cab Portal Routes (Independent layout, driver-facing, no owner login required) */}
          <Route path="/driver" element={<DriverPortalPage />} />
          <Route path="/driver/register" element={<DriverRegisterPage />} />
          <Route path="/driver/auth" element={<DriverAuthPage />} />
          <Route path="/driver/monitoring" element={<DriverMonitoringPage />} />

          {/* Owner / Fleet Manager Portal Routes (Protected by Owner Auth) */}
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <AppLayout />
              </ProtectedRoute>
            }
          >
            <Route index element={<DashboardPage />} />
            <Route path="dashboard" element={<DashboardPage />} />
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
      </AuthProvider>
    </BrowserRouter>
  );
}


