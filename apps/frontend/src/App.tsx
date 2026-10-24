import { Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider } from './contexts/AuthContext';
import ProtectedRoute from './components/ProtectedRoute';
import GuestRoute from './components/GuestRoute';
import Layout from './components/Layout';
import SampleRoute from './components/SampleRoute';
import LoginPage from './pages/LoginPage';
import SignupPage from './pages/SignupPage';
import ForgotPasswordPage from './pages/ForgotPasswordPage';
import ResetPasswordPage from './pages/ResetPasswordPage';
import SsoCompletePage from './pages/SsoCompletePage';
import NotFoundPage from './pages/NotFoundPage';
import SupplierScanPage from './pages/SupplierScanPage';
import SapImportPage from './pages/SapImportPage';
import AcceptInvitePage from './pages/AcceptInvitePage';
import DashboardPage from './pages/DashboardPage';
import RiskListPage from './pages/RiskListPage';
import RiskDetailPage from './pages/RiskDetailPage';
import NewAssessmentPage from './pages/NewAssessmentPage';
import RecommendationsPage from './pages/RecommendationsPage';
import SuppliersPage from './pages/SuppliersPage';
import AlertsPage from './pages/AlertsPage';
import SupplyChainMapPage from './pages/SupplyChainMapPage';
import PredictionsPage from './pages/PredictionsPage';
import EventsPage from './pages/EventsPage';
import IntelligenceFeedPage from './pages/IntelligenceFeedPage';
import SimulatorPage from './pages/SimulatorPage';
import ProcurementPage from './pages/ProcurementPage';
import ComponentsPage from './pages/ComponentsPage';
import SettingsPage from './pages/SettingsPage';
import AuditLogPage from './pages/AuditLogPage';
import IntegrationsPage from './pages/IntegrationsPage';
import SupplierAssessmentsPage from './pages/SupplierAssessmentsPage';
import PortalPage from './pages/PortalPage';
import RegulatoryWatchPage from './pages/RegulatoryWatchPage';
import WarRoomPage from './pages/WarRoomPage';

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        {/* Guest-only routes — redirect to dashboard if already logged in */}
        <Route element={<GuestRoute />}>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/signup" element={<SignupPage />} />
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
        </Route>

        {/* Protected routes — require authentication */}
        <Route element={<ProtectedRoute />}>
          <Route element={<Layout />}>
            <Route index element={<Navigate to="/dashboard" replace />} />
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/risks" element={<RiskListPage />} />
            <Route path="/risks/:id" element={<RiskDetailPage />} />
            <Route path="/assessments/new" element={<NewAssessmentPage />} />
            <Route path="/recommendations" element={<RecommendationsPage />} />
            <Route path="/suppliers" element={<SuppliersPage />} />
            <Route path="/supplier-assessments" element={<SupplierAssessmentsPage />} />
            <Route path="/scan" element={<SupplierScanPage />} />
            <Route path="/suppliers/import/sap" element={<SapImportPage />} />
            <Route path="/alerts" element={<AlertsPage />} />
            <Route path="/supply-chain" element={<SupplyChainMapPage />} />
            <Route path="/predictions" element={<SampleRoute><PredictionsPage /></SampleRoute>} />
            <Route path="/events" element={<EventsPage />} />
            <Route path="/intelligence" element={<IntelligenceFeedPage />} />
            <Route path="/regulatory-watch" element={<RegulatoryWatchPage />} />
            <Route path="/war-room" element={<WarRoomPage />} />
            <Route path="/simulator" element={<SampleRoute><SimulatorPage /></SampleRoute>} />
            <Route path="/procurement" element={<SampleRoute><ProcurementPage /></SampleRoute>} />
            <Route path="/components" element={<SampleRoute><ComponentsPage /></SampleRoute>} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/audit" element={<AuditLogPage />} />
            <Route path="/integrations" element={<IntegrationsPage />} />
          </Route>
        </Route>

        {/* Invitation links: public, whether or not someone is signed in on this browser */}
        <Route path="/invite" element={<AcceptInvitePage />} />
        <Route path="/reset-password" element={<ResetPasswordPage />} />
        <Route path="/sso/complete" element={<SsoCompletePage />} />
        {/* The supplier portal: no account, the link's token is the key (pages/PortalPage.tsx). */}
        <Route path="/portal" element={<PortalPage />} />

        {/* 404 catch-all */}
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </AuthProvider>
  );
}
