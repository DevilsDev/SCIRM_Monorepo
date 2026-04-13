import { useState } from 'react';
import { Link } from 'react-router-dom';
import SeverityBadge from '../components/SeverityBadge';
import Pagination from '../components/Pagination';
import { useRisks } from '../hooks/useRisks';

const PAGE_SIZE = 20;

export default function RiskListPage() {
  const [currentPage, setCurrentPage] = useState(1);
  const [severityFilter, setSeverityFilter] = useState('');

  const { risks, totalCount, loading, error } = useRisks({
    limit: PAGE_SIZE,
    offset: (currentPage - 1) * PAGE_SIZE,
    severity: severityFilter || undefined,
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Risk Overview</h1>
          <p className="text-sm text-gray-500 mt-1">{totalCount} risks tracked</p>
        </div>
        <Link
          to="/assessments/new"
          className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors"
        >
          New Assessment
        </Link>
      </div>

      {/* Filters */}
      <div className="flex gap-3">
        <select
          value={severityFilter}
          onChange={(e) => {
            setSeverityFilter(e.target.value);
            setCurrentPage(1);
          }}
          className="px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
        >
          <option value="">All Severities</option>
          <option value="critical">Critical</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
        {loading ? (
          <p className="p-6 text-sm text-gray-400">Loading risks...</p>
        ) : error ? (
          <p className="p-6 text-sm text-red-500">{error}</p>
        ) : risks.length === 0 ? (
          <p className="p-6 text-sm text-gray-400">No risks found.</p>
        ) : (
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Title</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Severity</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Probability</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Impact</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Category</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Detected</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {risks.map((risk) => (
                <tr key={risk.id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-6 py-4">
                    <Link to={`/risks/${risk.id}`} className="text-sm font-medium text-blue-600 hover:text-blue-800">
                      {risk.title}
                    </Link>
                  </td>
                  <td className="px-6 py-4">
                    <SeverityBadge severity={risk.severity} />
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-500">
                    {(risk.probability * 100).toFixed(0)}%
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-500">
                    {risk.impact_score.toFixed(1)}
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-500 capitalize">
                    {risk.risk_category}
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-500">
                    {new Date(risk.detected_at).toLocaleDateString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        <Pagination
          currentPage={currentPage}
          totalItems={totalCount}
          pageSize={PAGE_SIZE}
          onPageChange={setCurrentPage}
        />
      </div>
    </div>
  );
}
