import { Link, useLocation } from 'react-router-dom';
import { ChevronRightIcon, HomeIcon } from '@heroicons/react/24/solid';

const ROUTE_LABELS: Record<string, string> = {
  dashboard: 'Dashboard',
  risks: 'Risks',
  suppliers: 'Suppliers',
  components: 'Components',
  'supply-chain': 'Supply Chain',
  predictions: 'Predictions',
  events: 'Risk Events',
  intelligence: 'Intel Feed',
  simulator: 'Simulator',
  procurement: 'Procurement',
  alerts: 'Alerts',
  assessments: 'Assessments',
  recommendations: 'Recommendations',
  new: 'New Assessment',
};

export default function Breadcrumbs() {
  const location = useLocation();
  const segments = location.pathname.split('/').filter(Boolean);

  if (segments.length <= 1) return null; // Don't show on top-level pages

  return (
    <nav className="flex items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400 mb-4" aria-label="Breadcrumb">
      <Link to="/dashboard" className="hover:text-gray-700 dark:hover:text-gray-200 transition-colors">
        <HomeIcon className="h-3.5 w-3.5" />
      </Link>
      {segments.map((segment, i) => {
        const path = '/' + segments.slice(0, i + 1).join('/');
        const label = ROUTE_LABELS[segment] || segment;
        const isLast = i === segments.length - 1;

        return (
          <span key={path} className="flex items-center gap-1.5">
            <ChevronRightIcon className="h-3 w-3 text-gray-300 dark:text-gray-600" />
            {isLast ? (
              <span className="font-medium text-gray-700 dark:text-gray-200">{label}</span>
            ) : (
              <Link to={path} className="hover:text-gray-700 dark:hover:text-gray-200 transition-colors">
                {label}
              </Link>
            )}
          </span>
        );
      })}
    </nav>
  );
}
