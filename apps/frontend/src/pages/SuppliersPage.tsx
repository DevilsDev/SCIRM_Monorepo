import { useEffect, useState } from 'react';
import { api, Supplier } from '../services/api';
import RadarChart from '../components/d3/RadarChart';
import { XMarkIcon } from '@heroicons/react/24/outline';

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
      <span className="text-sm font-medium text-gray-700 dark:text-gray-300">{score.toFixed(0)}</span>
    </div>
  );
}

interface DimensionScore {
  dimension: string;
  label: string;
  score: number;
  confidence: number;
  trend: string;
  reasoning: string;
}

export default function SuppliersPage() {
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [tierFilter, setTierFilter] = useState('');
  const [selectedSupplier, setSelectedSupplier] = useState<Supplier | null>(null);
  const [radarData, setRadarData] = useState<DimensionScore[]>([]);
  const [scoringLoading, setScoringLoading] = useState(false);

  useEffect(() => {
    api
      .getSuppliers({ risk_tier: tierFilter || undefined })
      .then((data) => setSuppliers(data.suppliers || []))
      .catch((err) => setError(err.message || 'Failed to load suppliers'))
      .finally(() => setLoading(false));
  }, [tierFilter]);

  const handleSupplierClick = async (supplier: Supplier) => {
    setSelectedSupplier(supplier);
    setScoringLoading(true);
    setRadarData([]);
    try {
      const result = await api.scoreSupplierRisk(supplier.name, {
        country_code: supplier.country_code,
        region: supplier.region,
        risk_score: supplier.risk_score,
        supplier_type: supplier.supplier_type,
      });
      setRadarData(result.dimension_scores || []);
    } catch {
      setRadarData([]);
    } finally {
      setScoringLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Suppliers</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">{suppliers.length} suppliers tracked — click a supplier for 7-dimension risk profile</p>
        </div>
      </div>

      <div className="flex gap-3">
        <select
          value={tierFilter}
          onChange={(e) => setTierFilter(e.target.value)}
          className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm bg-white dark:bg-gray-800 focus:ring-2 focus:ring-blue-500 outline-none"
        >
          <option value="">All Risk Tiers</option>
          <option value="low">Low</option>
          <option value="medium">Medium</option>
          <option value="high">High</option>
        </select>
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 overflow-hidden">
        {loading ? (
          <p className="p-6 text-sm text-gray-400">Loading suppliers...</p>
        ) : error ? (
          <p className="p-6 text-sm text-red-500">{error}</p>
        ) : suppliers.length === 0 ? (
          <p className="p-6 text-sm text-gray-400">No suppliers found.</p>
        ) : (
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50 dark:bg-gray-900">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Name</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Code</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Type</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Region</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Risk Score</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Risk Tier</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {suppliers.map((s) => (
                <tr
                  key={s.id}
                  className="hover:bg-blue-50 cursor-pointer transition-colors"
                  onClick={() => handleSupplierClick(s)}
                >
                  <td className="px-6 py-4 text-sm font-medium text-blue-600">{s.name}</td>
                  <td className="px-6 py-4 text-sm text-gray-500 dark:text-gray-400 font-mono">{s.supplier_code}</td>
                  <td className="px-6 py-4 text-sm text-gray-500 dark:text-gray-400 capitalize">{s.supplier_type.replace('_', ' ')}</td>
                  <td className="px-6 py-4 text-sm text-gray-500 dark:text-gray-400">{s.country_code} {s.region}</td>
                  <td className="px-6 py-4"><RiskScoreBar score={s.risk_score} /></td>
                  <td className="px-6 py-4">
                    <span className={`inline-flex px-2.5 py-0.5 rounded-full text-xs font-medium capitalize ${tierColors[s.risk_tier] || 'bg-gray-100 dark:bg-gray-700 text-gray-800'}`}>
                      {s.risk_tier}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* 7-Dimension Risk Profile Modal */}
      {selectedSupplier && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50" onClick={() => setSelectedSupplier(null)}>
          <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-2xl p-6 max-w-lg w-full mx-4" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="text-lg font-bold text-gray-900 dark:text-white">{selectedSupplier.name}</h2>
                <p className="text-xs text-gray-500 dark:text-gray-400">7-Dimension Risk Profile — {selectedSupplier.country_code} {selectedSupplier.region}</p>
              </div>
              <button onClick={() => setSelectedSupplier(null)} className="p-1 hover:bg-gray-100 dark:bg-gray-700 rounded-lg">
                <XMarkIcon className="h-5 w-5 text-gray-400" />
              </button>
            </div>

            {scoringLoading ? (
              <div className="flex items-center justify-center h-64">
                <p className="text-sm text-gray-400">Scoring across 7 dimensions...</p>
              </div>
            ) : radarData.length > 0 ? (
              <>
                <div className="flex justify-center">
                  <RadarChart data={radarData} size={280} />
                </div>
                <div className="mt-4 grid grid-cols-2 gap-2">
                  {radarData.map((d) => (
                    <div key={d.dimension} className="flex items-center justify-between px-3 py-2 bg-gray-50 dark:bg-gray-900 rounded-lg">
                      <span className="text-xs font-medium text-gray-700 dark:text-gray-300">{d.label}</span>
                      <div className="flex items-center gap-2">
                        <span className={`text-xs font-bold ${d.score > 65 ? 'text-red-600' : d.score > 40 ? 'text-yellow-600' : 'text-green-600'}`}>
                          {d.score.toFixed(0)}
                        </span>
                        <span className="text-[9px] text-gray-400 capitalize">{d.trend}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <p className="text-sm text-gray-400 text-center py-8">No scoring data available</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
