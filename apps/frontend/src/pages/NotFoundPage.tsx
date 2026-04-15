import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

export default function NotFoundPage() {
  const { t } = useTranslation();

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900">
      <div className="text-center">
        <p className="text-7xl font-bold text-gray-300 dark:text-gray-700">404</p>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white mt-4">{t('common.pageNotFound', 'Page Not Found')}</h1>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-2">{t('common.pageNotFoundDesc', "The page you're looking for doesn't exist or has been moved.")}</p>
        <div className="flex gap-3 justify-center mt-6">
          <Link to="/dashboard" className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700">
            {t('common.goToDashboard', 'Go to Dashboard')}
          </Link>
          <Link to="/login" className="px-4 py-2 bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg text-sm font-medium hover:bg-gray-300 dark:hover:bg-gray-600">
            {t('auth.signIn', 'Sign In')}
          </Link>
        </div>
      </div>
    </div>
  );
}
