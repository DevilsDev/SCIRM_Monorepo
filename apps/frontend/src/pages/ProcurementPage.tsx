import { useEffect, useState } from 'react';
import { api } from '../services/api';
import SeverityBadge from '../components/SeverityBadge';

export default function ProcurementPage() {
  const [actions, setActions] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [evaluating, setEvaluating] = useState(false);

  const fetchActions = () => {
    api.getProcurementActions()
      .then((data) => setActions(data.actions || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchActions(); }, []);

  const handleEvaluate = async () => {
    setEvaluating(true);
    try {
      const suppliersData = await api.getSuppliers();
      const suppliers = suppliersData.suppliers || [];
      await api.evaluateProcurement(suppliers, 60);
      fetchActions();
    } catch {} finally { setEvaluating(false); }
  };

  const proposed = actions.filter((a) => a.status === 'proposed');
  const executed = actions.filter((a) => a.status !== 'proposed');

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Procurement Agent</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">Autonomous sourcing — evaluates supplier risk and proposes alternatives</p>
        </div>
        <button onClick={handleEvaluate} disabled={evaluating} className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors">
          {evaluating ? 'Evaluating...' : 'Evaluate Suppliers'}
        </button>
      </div>

      {/* Summary */}
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-4 text-center">
          <p className="text-3xl font-bold text-gray-900 dark:text-white">{actions.length}</p>
          <p className="text-xs text-gray-500 dark:text-gray-400">Total Actions</p>
        </div>
        <div className="bg-yellow-50 border border-yellow-200 rounded-xl p-4 text-center">
          <p className="text-3xl font-bold text-yellow-700">{proposed.length}</p>
          <p className="text-xs text-yellow-600">Pending Approval</p>
        </div>
        <div className="bg-green-50 border border-green-200 rounded-xl p-4 text-center">
          <p className="text-3xl font-bold text-green-700">
            {actions.reduce((s, a) => s + (a.risk_reduction || 0), 0).toFixed(0)}
          </p>
          <p className="text-xs text-green-600">Total Risk Reduction</p>
        </div>
      </div>

      {/* Proposed Actions */}
      {proposed.length > 0 && (
        <div>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">Proposed Actions</h2>
          <div className="space-y-3">
            {proposed.map((action) => (
              <div key={action.id} className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-yellow-200 p-5">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <h3 className="text-sm font-semibold text-gray-900 dark:text-white">{action.title}</h3>
                    <p className="text-xs text-gray-600 dark:text-gray-300 mt-1">{action.description}</p>
                    <div className="flex gap-4 mt-3 text-xs text-gray-500 dark:text-gray-400">
                      <span>Risk: {action.current_supplier_risk?.toFixed(0)} → {action.proposed_supplier_risk?.toFixed(0) || '?'}</span>
                      {action.risk_reduction > 0 && <span className="text-green-600">↓ {action.risk_reduction.toFixed(0)} points</span>}
                      {action.alternatives_count > 0 && <span>{action.alternatives_count} alternatives</span>}
                    </div>
                  </div>
                  <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800 capitalize">{action.status}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Action History */}
      {executed.length > 0 && (
        <div>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">Action History</h2>
          <div className="space-y-2">
            {executed.map((action) => (
              <div key={action.id} className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-4 flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-gray-900 dark:text-white">{action.title}</p>
                  <p className="text-xs text-gray-500 dark:text-gray-400">{new Date(action.created_at).toLocaleString()}</p>
                </div>
                <span className={`px-2 py-0.5 rounded-full text-xs font-medium capitalize ${action.status === 'approved' ? 'bg-green-100 text-green-800' : action.status === 'rejected' ? 'bg-red-100 text-red-800' : 'bg-gray-100 dark:bg-gray-700 text-gray-800'}`}>
                  {action.status}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {loading ? (
        <p className="text-sm text-gray-400">Loading procurement actions...</p>
      ) : actions.length === 0 ? (
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-8 text-center">
          <p className="text-sm text-gray-400">No procurement actions yet. Click "Evaluate Suppliers" to analyze your supply chain and generate sourcing proposals.</p>
        </div>
      ) : null}
    </div>
  );
}
