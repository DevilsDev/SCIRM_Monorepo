import { Link } from 'react-router-dom';
import {
  ShieldExclamationIcon,
  ExclamationTriangleIcon,
  ChartBarIcon,
  CheckCircleIcon,
} from '@heroicons/react/24/outline';
import { useTranslation } from 'react-i18next';
import MetricCard from '../components/MetricCard';
import SeverityBadge from '../components/SeverityBadge';
import SeverityChart from '../components/SeverityChart';
import RiskHeatmap from '../components/d3/RiskHeatmap';
import { SkeletonCard, SkeletonChart } from '../components/Skeleton';
import { useRisks } from '../hooks/useRisks';
import { useAutoRefresh } from '../hooks/useAutoRefresh';
import { useTheme } from '../contexts/ThemeContext';
import { useAuth } from '../contexts/AuthContext';
import { useToast } from '../components/Toast';
import { useEffect, useRef, useState } from 'react';
import { DateRangePicker } from '../components/ui';

export default function DashboardPage() {
  const { risks, totalCount, loading, refetch } = useRisks({ limit: 50 });
  const { theme } = useTheme();
  const { user } = useAuth();
  const { addToast } = useToast();
  const { t } = useTranslation();
  const prevCount = useRef(totalCount);
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');

  // Auto-refresh every 30 seconds
  useAutoRefresh(refetch, 30000);

  // Toast when new risks appear
  useEffect(() => {
    if (prevCount.current > 0 && totalCount > prevCount.current) {
      addToast('warning', 'New risks detected', `${totalCount - prevCount.current} new risk(s) added to your supply chain.`);
    }
    prevCount.current = totalCount;
  }, [totalCount]);

  const criticalCount = risks.filter((r) => r.severity === 'critical').length;
  const highCount = risks.filter((r) => r.severity === 'high').length;

  const severityData = [
    { name: 'critical', value: risks.filter((r) => r.severity === 'critical').length },
    { name: 'high', value: risks.filter((r) => r.severity === 'high').length },
    { name: 'medium', value: risks.filter((r) => r.severity === 'medium').length },
    { name: 'low', value: risks.filter((r) => r.severity === 'low').length },
  ];

  const categories = [...new Set(risks.map((r) => r.risk_category))].filter(Boolean);
  const heatmapData = categories.flatMap((cat) =>
    ['low', 'medium', 'high', 'critical'].map((sev) => ({
      category: cat,
      severity: sev,
      value: risks.filter((r) => r.risk_category === cat && r.severity === sev).length,
    }))
  );

  const isAdmin = user?.roles?.includes('admin');
  const isViewer = user?.roles?.includes('viewer') && !user?.roles?.includes('admin') && !user?.roles?.includes('analyst');

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{t('dashboard.title', 'Dashboard')}</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            {t('dashboard.subtitle', 'Supply chain risk overview')}
            <span className="text-xs ml-2 text-gray-400">{t('dashboard.autoRefresh', 'Auto-refreshes every 30s')}</span>
          </p>
        </div>
        {!isViewer && (
          <div className="flex gap-2">
            <Link to="/assessments/new" className="px-3 py-1.5 bg-blue-600 text-white rounded-lg text-xs font-medium hover:bg-blue-700">
              {t('dashboard.newAssessmentBtn', 'New Assessment')}
            </Link>
            <Link to="/simulator" className="px-3 py-1.5 bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg text-xs font-medium hover:bg-gray-300 dark:hover:bg-gray-600">
              {t('dashboard.simulatorBtn', 'Simulator')}
            </Link>
          </div>
        )}
      </div>

      {/* Date Range Filter */}
      <div className="flex items-center gap-3">
        <span className="text-xs text-gray-500 dark:text-gray-400">{t('dashboard.dateRange', 'Date range')}:</span>
        <DateRangePicker from={dateFrom} to={dateTo} onFromChange={setDateFrom} onToChange={setDateTo} />
        {(dateFrom || dateTo) && (
          <button onClick={() => { setDateFrom(''); setDateTo(''); }} className="text-xs text-blue-600 hover:text-blue-800">
            {t('common.clear', 'Clear')}
          </button>
        )}
      </div>

      {/* Metrics */}
      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => <SkeletonCard key={i} />)}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <MetricCard title={t('dashboard.totalRisks', 'Total Risks')} value={String(totalCount)} icon={ShieldExclamationIcon} color="blue" href="/risks" />
          <MetricCard title={t('dashboard.criticalRisks', 'Critical Risks')} value={String(criticalCount)} icon={ExclamationTriangleIcon} color="red" href="/risks?severity=critical" />
          <MetricCard title={t('dashboard.highRisks', 'High Risks')} value={String(highCount)} icon={ChartBarIcon} color="yellow" href="/risks?severity=high" />
          <MetricCard title={t('dashboard.monitored', 'Monitored')} value={String(totalCount)} icon={CheckCircleIcon} color="green" href="/suppliers" />
        </div>
      )}

      {/* Charts */}
      {loading ? (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <SkeletonChart height={240} />
          <SkeletonChart height={240} />
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">{t('dashboard.severityBreakdown', 'Risk Severity Breakdown')}</h2>
            <SeverityChart key={`donut-${theme}`} data={severityData} />
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">{t('dashboard.riskHeatmap', 'Risk Heatmap')}</h2>
            <RiskHeatmap key={`heatmap-${theme}`} data={heatmapData} height={220} />
          </div>
        </div>
      )}

      {/* {t('dashboard.recentRisks', 'Recent Risks')} with contextual actions */}
      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">{t('dashboard.recentRisks', 'Recent Risks')}</h2>
          <Link to="/risks" className="text-xs text-blue-600 hover:text-blue-800 font-medium">{t('dashboard.viewAll', 'View all')} &rarr;</Link>
        </div>
        {loading ? (
          <div className="space-y-3">{[...Array(4)].map((_, i) => <SkeletonCard key={i} />)}</div>
        ) : risks.length === 0 ? (
          <p className="text-sm text-gray-400">{t('dashboard.noRisks', 'No risks found. Run an assessment to get started.')}</p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {risks.slice(0, 8).map((risk) => (
              <div key={risk.id} className="flex items-center justify-between p-3 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors border border-gray-100 dark:border-gray-700">
                <Link to={`/risks/${risk.id}`} className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-gray-900 dark:text-white truncate">{risk.title}</p>
                  <p className="text-xs text-gray-500 dark:text-gray-400 capitalize">{risk.risk_category}</p>
                </Link>
                <div className="flex items-center gap-2">
                  <SeverityBadge severity={risk.severity} />
                  {!isViewer && (
                    <Link to={`/simulator`} className="text-[10px] text-blue-500 hover:text-blue-700 whitespace-nowrap" title={t('dashboard.simulate', 'Simulate')}>
                      {t('dashboard.simulate', 'Simulate')}
                    </Link>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Admin-only: quick links */}
      {isAdmin && (
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">{t('dashboard.adminActions', 'Admin Quick Actions')}</h2>
          <div className="flex flex-wrap gap-2">
            <Link to="/procurement" className="px-3 py-1.5 bg-purple-100 text-purple-700 rounded-lg text-xs font-medium hover:bg-purple-200">{t('dashboard.procurementAgent', 'Procurement Agent')}</Link>
            <Link to="/intelligence" className="px-3 py-1.5 bg-cyan-100 text-cyan-700 rounded-lg text-xs font-medium hover:bg-cyan-200">{t('dashboard.intelFeed', 'Intel Feed')}</Link>
            <Link to="/events" className="px-3 py-1.5 bg-orange-100 text-orange-700 rounded-lg text-xs font-medium hover:bg-orange-200">{t('dashboard.riskEvents', 'Risk Events')}</Link>
            <Link to="/components" className="px-3 py-1.5 bg-green-100 text-green-700 rounded-lg text-xs font-medium hover:bg-green-200">{t('dashboard.componentsBtn', 'Components')}</Link>
          </div>
        </div>
      )}
    </div>
  );
}
