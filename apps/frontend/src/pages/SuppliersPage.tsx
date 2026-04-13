import { useEffect, useState } from 'react';
import { api, Supplier } from '../services/api';

const tierColors: Record<string, string> = {
  low: 'bg-green-100 text-green-800',
  medium: 'bg-yellow-100 text-yellow-800',
  high: 'bg-orange-100 text-orange-800',
  critical: 'bg-red-100 text-red-800',
};

function RiskScoreBar({ score }: { score: number }) {
  const color = score < 40 ? 'bg-green-500' : score < 65 ? 'bg-yellow-500' : score < 80 ? 'bg-orange-500' : 'bg-red-500';
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 bg-gray-200 rounded-full h-2 max-w-[120px]">
        <div className={`${color} rounded-full h-2`} style={{ width: `${score}%` }} />
      </div>
      <span className="text-sm font-medium text-gray-700">{score.toFixed(0)}</span>
    </div>
  );
}

export default function SuppliersPage() {
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [tierFilter, setTierFilter] = useState('');

  useEffect(() => {
    api
      .getSuppliers({ risk_tier: tierFilter || undefined })
      .then((data) => setSuppliers(data.suppliers || []))
      .catch((err) => setError(err.message || 'Failed to load suppliers'))
      .finally(() => setLoading(false));
  }, [tierFilter]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Suppliers</h1>
          <p className="text-sm text-gray-500 mt-1">{suppliers.length} suppliers tracked</p>
        </div>
      </div>

      <div className="flex gap-3">
        <select
          value={tierFilter}
          onChange={(e) => setTierFilter(e.target.value)}
          className="px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white focus:ring-2 focus:ring-blue-500 outline-none"
        >
          <option value="">All Risk Tiers</option>
          <option value="low">Low</option>
          <option value="medium">Medium</option>
          <option value="high">High</option>
        </select>
      </div>

      <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
        {loading ? (
          <p className="p-6 text-sm text-gray-400">Loading suppliers...</p>
        ) : error ? (
          <p className="p-6 text-sm text-red-500">{error}</p>
        ) : suppliers.length === 0 ? (
          <p className="p-6 text-sm text-gray-400">No suppliers found.</p>
        ) : (
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Name</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Code</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Type</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Region</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Risk Score</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Risk Tier</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Contact</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {suppliers.map((s) => (
                <tr key={s.id} className="hover:bg-gray-50">
                  <td className="px-6 py-4 text-sm font-medium text-gray-900">{s.name}</td>
                  <td className="px-6 py-4 text-sm text-gray-500 font-mono">{s.supplier_code}</td>
                  <td className="px-6 py-4 text-sm text-gray-500 capitalize">{s.supplier_type.replace('_', ' ')}</td>
                  <td className="px-6 py-4 text-sm text-gray-500">
                    {s.country_code && <span className="mr-1">{s.country_code}</span>}
                    {s.region}
                  </td>
                  <td className="px-6 py-4"><RiskScoreBar score={s.risk_score} /></td>
                  <td className="px-6 py-4">
                    <span className={`inline-flex px-2.5 py-0.5 rounded-full text-xs font-medium capitalize ${tierColors[s.risk_tier] || 'bg-gray-100 text-gray-800'}`}>
                      {s.risk_tier}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-500">{s.contact_name || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
