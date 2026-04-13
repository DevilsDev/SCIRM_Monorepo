import { Link } from 'react-router-dom';
import {
  ShieldExclamationIcon,
  ExclamationTriangleIcon,
  ChartBarIcon,
  CheckCircleIcon,
} from '@heroicons/react/24/outline';
import MetricCard from '../components/MetricCard';
import SeverityBadge from '../components/SeverityBadge';
import SeverityChart from '../components/SeverityChart';
import { useRisks } from '../hooks/useRisks';

export default function DashboardPage() {
  const { risks, totalCount, loading } = useRisks({ limit: 50 });

  const criticalCount = risks.filter((r) => r.severity === 'critical').length;
  const highCount = risks.filter((r) => r.severity === 'high').length;

  const severityData = [
    { name: 'critical', value: risks.filter((r) => r.severity === 'critical').length },
    { name: 'high', value: risks.filter((r) => r.severity === 'high').length },
    { name: 'medium', value: risks.filter((r) => r.severity === 'medium').length },
    { name: 'low', value: risks.filter((r) => r.severity === 'low').length },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
        <p className="text-sm text-gray-500 mt-1">Supply chain risk overview</p>
      </div>

      {/* Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          title="Total Risks"
          value={loading ? '...' : String(totalCount)}
          icon={ShieldExclamationIcon}
          color="blue"
        />
        <MetricCard
          title="Critical Risks"
          value={loading ? '...' : String(criticalCount)}
          icon={ExclamationTriangleIcon}
          color="red"
        />
        <MetricCard
          title="High Risks"
          value={loading ? '...' : String(highCount)}
          icon={ChartBarIcon}
          color="yellow"
        />
        <MetricCard
          title="Monitored"
          value={loading ? '...' : String(totalCount)}
          icon={CheckCircleIcon}
          color="green"
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Severity Chart */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Risk Severity Breakdown</h2>
          <SeverityChart data={severityData} />
        </div>

        {/* Recent Risks */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Recent Risks</h2>
          {loading ? (
            <p className="text-sm text-gray-400">Loading...</p>
          ) : risks.length === 0 ? (
            <p className="text-sm text-gray-400">No risks found. Run an assessment to get started.</p>
          ) : (
            <div className="space-y-3">
              {risks.slice(0, 8).map((risk) => (
                <Link
                  key={risk.id}
                  to={`/risks/${risk.id}`}
                  className="flex items-center justify-between p-3 rounded-lg hover:bg-gray-50 transition-colors"
                >
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-gray-900 truncate">{risk.title}</p>
                    <p className="text-xs text-gray-500 capitalize">{risk.risk_category}</p>
                  </div>
                  <SeverityBadge severity={risk.severity} />
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
