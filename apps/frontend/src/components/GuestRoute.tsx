import { Navigate, Outlet } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

/**
 * GuestRoute — only accessible when NOT authenticated.
 * Redirects authenticated users to /dashboard.
 * Used for /login, /signup, /forgot-password.
 */
export default function GuestRoute() {
  const { isAuthenticated } = useAuth();

  if (isAuthenticated) {
    return <Navigate to="/dashboard" replace />;
  }

  return <Outlet />;
}
