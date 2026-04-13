import { Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider } from './contexts/AuthContext';
import ProtectedRoute from './components/ProtectedRoute';
import Layout from './components/Layout';
import LoginPage from './pages/LoginPage';
import DashboardPage from './pages/DashboardPage';
import RiskListPage from './pages/RiskListPage';
import RiskDetailPage from './pages/RiskDetailPage';
import NewAssessmentPage from './pages/NewAssessmentPage';
import RecommendationsPage from './pages/RecommendationsPage';

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route element={<ProtectedRoute />}>
          <Route element={<Layout />}>
            <Route index element={<Navigate to="/dashboard" replace />} />
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/risks" element={<RiskListPage />} />
            <Route path="/risks/:id" element={<RiskDetailPage />} />
            <Route path="/assessments/new" element={<NewAssessmentPage />} />
            <Route path="/recommendations" element={<RecommendationsPage />} />
          </Route>
        </Route>
      </Routes>
    </AuthProvider>
  );
}
