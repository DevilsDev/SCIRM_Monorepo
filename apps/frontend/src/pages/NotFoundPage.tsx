import { Link } from 'react-router-dom';

export default function NotFoundPage() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900">
      <div className="text-center">
        <p className="text-7xl font-bold text-gray-300 dark:text-gray-700">404</p>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white mt-4">Page Not Found</h1>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-2">The page you're looking for doesn't exist or has been moved.</p>
        <div className="flex gap-3 justify-center mt-6">
          <Link to="/dashboard" className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700">
            Go to Dashboard
          </Link>
          <Link to="/login" className="px-4 py-2 bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg text-sm font-medium hover:bg-gray-300 dark:hover:bg-gray-600">
            Sign In
          </Link>
        </div>
      </div>
    </div>
  );
}
