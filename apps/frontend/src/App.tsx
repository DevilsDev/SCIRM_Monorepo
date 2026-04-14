import { Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider } from './contexts/AuthContext';
import ProtectedRoute from './components/ProtectedRoute';
import Layout from './components/Layout';
import LoginPage from './pages/LoginPage';
import SignupPage from './pages/SignupPage';
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

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/signup" element={<SignupPage />} />
        <Route element={<ProtectedRoute />}>
          <Route element={<Layout />}>
            <Route index element={<Navigate to="/dashboard" replace />} />
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/risks" element={<RiskListPage />} />
            <Route path="/risks/:id" element={<RiskDetailPage />} />
            <Route path="/assessments/new" element={<NewAssessmentPage />} />
            <Route path="/recommendations" element={<RecommendationsPage />} />
            <Route path="/suppliers" element={<SuppliersPage />} />
            <Route path="/alerts" element={<AlertsPage />} />
            <Route path="/supply-chain" element={<SupplyChainMapPage />} />
            <Route path="/predictions" element={<PredictionsPage />} />
            <Route path="/events" element={<EventsPage />} />
            <Route path="/intelligence" element={<IntelligenceFeedPage />} />
            <Route path="/simulator" element={<SimulatorPage />} />
            <Route path="/procurement" element={<ProcurementPage />} />
          </Route>
        </Route>
      </Routes>
    </AuthProvider>
  );
}
