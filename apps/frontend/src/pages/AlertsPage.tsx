import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api, Alert } from '../services/api';
import SeverityBadge from '../components/SeverityBadge';

export default function AlertsPage() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const { t } = useTranslation();

  useEffect(() => {
    api
      .getAlerts({ status: statusFilter || undefined })
      .then((data) => setAlerts(data.alerts || []))
      .catch((err) => setError(err.message || 'Failed to load alerts'))
      .finally(() => setLoading(false));
  }, [statusFilter]);

  const activeCount = alerts.filter((a) => a.status === 'active').length;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{t('alerts.title', 'Alerts')}</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            {t('alerts.activeCount', '{{count}} active alert(s) of {{total}} total', { count: activeCount, total: alerts.length })}
          </p>
        </div>
      </div>

      <div className="flex gap-3">
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm bg-white dark:bg-gray-800 focus:ring-2 focus:ring-blue-500 outline-none"
        >
          <option value="">{t('alerts.allStatuses', 'All Statuses')}</option>
          <option value="active">{t('alerts.active', 'Active')}</option>
          <option value="acknowledged">{t('alerts.acknowledged', 'Acknowledged')}</option>
          <option value="resolved">{t('alerts.resolved', 'Resolved')}</option>
        </select>
      </div>

      <div className="space-y-3">
        {loading ? (
          <p className="text-sm text-gray-400">{t('common.loading', 'Loading...')}</p>
        ) : error ? (
          <p className="text-sm text-red-500">{error}</p>
        ) : alerts.length === 0 ? (
          <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-8 text-center">
            <p className="text-sm text-gray-400">{t('alerts.noAlerts', 'No alerts. Run an assessment to generate risk alerts.')}</p>
          </div>
        ) : (
          alerts.map((alert) => (
            <div
              key={alert.id}
              className={`bg-white dark:bg-gray-800 rounded-xl shadow-sm border p-5 ${
                alert.status === 'active' ? 'border-red-200' : 'border-gray-200 dark:border-gray-700'
              }`}
            >
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center gap-3">
                    <h3 className="text-sm font-semibold text-gray-900 dark:text-white">{alert.title}</h3>
                    <SeverityBadge severity={alert.severity} />
                    <span
                      className={`px-2 py-0.5 rounded-full text-xs font-medium capitalize ${
                        alert.status === 'active'
                          ? 'bg-red-50 text-red-700'
                          : alert.status === 'acknowledged'
                          ? 'bg-blue-50 text-blue-700'
                          : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300'
                      }`}
                    >
                      {alert.status}
                    </span>
                  </div>
                  {alert.description && (
                    <p className="text-xs text-gray-600 dark:text-gray-300 mt-2">{alert.description}</p>
                  )}
                  <p className="text-xs text-gray-400 mt-2">
                    {new Date(alert.created_at).toLocaleString()}
                  </p>
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
