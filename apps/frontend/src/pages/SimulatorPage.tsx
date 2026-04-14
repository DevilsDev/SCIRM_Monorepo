import { useState } from 'react';
import { api } from '../services/api';
import AnimatedBars from '../components/d3/AnimatedBars';

const SUPPLIERS = ['Supplier Alpha', 'Supplier Beta', 'Supplier Gamma', 'Supplier Delta', 'Supplier Epsilon'];

export default function SimulatorPage() {
  const [selected, setSelected] = useState<string[]>(['Supplier Gamma']);
  const [severity, setSeverity] = useState('high');
  const [duration, setDuration] = useState(30);
  const [simCount, setSimCount] = useState(1000);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);

  const handleRun = async () => {
    setLoading(true);
    try {
      const data = await api.runSimulation({ disrupted_suppliers: selected, severity, duration_days: duration, num_simulations: simCount });
      setResult(data);
    } catch { setResult(null); }
    finally { setLoading(false); }
  };

  const toggleSupplier = (s: string) => setSelected((prev) => prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Digital Twin Simulator</h1>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">Monte Carlo simulation — model disruption scenarios across your supply chain</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Scenario Builder */}
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Scenario Builder</h2>

          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Disrupt Suppliers</label>
          <div className="space-y-2 mb-4">
            {SUPPLIERS.map((s) => (
              <label key={s} className="flex items-center gap-2 text-sm cursor-pointer">
                <input type="checkbox" checked={selected.includes(s)} onChange={() => toggleSupplier(s)} className="rounded border-gray-300 dark:border-gray-600" />
                {s}
              </label>
            ))}
          </div>

          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Severity</label>
          <select value={severity} onChange={(e) => setSeverity(e.target.value)} className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm mb-4">
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
            <option value="critical">Critical</option>
          </select>

          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Duration (days)</label>
          <input type="number" value={duration} onChange={(e) => setDuration(Number(e.target.value))} min={1} max={365} className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm mb-4" />

          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Simulations</label>
          <input type="number" value={simCount} onChange={(e) => setSimCount(Number(e.target.value))} min={100} max={10000} step={100} className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm mb-4" />

          <button onClick={handleRun} disabled={loading || !selected.length} className="w-full py-2.5 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors">
            {loading ? 'Simulating...' : `Run ${simCount.toLocaleString()} Simulations`}
          </button>
        </div>

        {/* Results */}
        <div className="lg:col-span-2 space-y-4">
          {result ? (
            <>
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-4 text-center">
                  <p className="text-2xl font-bold text-gray-900 dark:text-white">${(result.financial_impact_p50 / 1000).toFixed(0)}k</p>
                  <p className="text-xs text-gray-500 dark:text-gray-400">Median Impact (P50)</p>
                </div>
                <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-center">
                  <p className="text-2xl font-bold text-red-700">${(result.financial_impact_p95 / 1000).toFixed(0)}k</p>
                  <p className="text-xs text-red-600">Worst Case (P95)</p>
                </div>
                <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-4 text-center">
                  <p className="text-2xl font-bold text-gray-900 dark:text-white">{result.recovery_days_p50.toFixed(0)}d</p>
                  <p className="text-xs text-gray-500 dark:text-gray-400">Median Recovery</p>
                </div>
                <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-4 text-center">
                  <p className="text-2xl font-bold text-gray-900 dark:text-white">{result.suppliers_affected_mean.toFixed(1)}</p>
                  <p className="text-xs text-gray-500 dark:text-gray-400">Avg Suppliers Hit</p>
                </div>
              </div>

              {/* Financial Impact Distribution */}
              <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
                <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-3">Financial Impact Distribution ({result.num_simulations.toLocaleString()} simulations)</h3>
                <AnimatedBars
                  data={result.financial_histogram.map((h: any) => ({
                    name: `$${(h.bin_start / 1000).toFixed(0)}k`,
                    value: h.count,
                    color: h.bin_start > result.financial_impact_p95 ? '#ef4444' : h.bin_start > result.financial_impact_p50 ? '#f97316' : '#3b82f6',
                  })).filter((_: any, i: number) => i % 2 === 0)}
                  height={250}
                  valueLabel=""
                />
              </div>

              {/* Mitigation Actions */}
              <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
                <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-3">Recommended Mitigations</h3>
                <div className="space-y-2">
                  {result.mitigation_actions.map((m: any, i: number) => (
                    <div key={i} className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-900 rounded-lg">
                      <div>
                        <p className="text-sm font-medium text-gray-900 dark:text-white">{m.action}</p>
                        <p className="text-xs text-gray-500 dark:text-gray-400">{m.rationale}</p>
                      </div>
                      <div className="text-right">
                        <span className={`px-2 py-0.5 rounded-full text-xs font-medium capitalize ${m.priority === 'critical' ? 'bg-red-100 text-red-800' : m.priority === 'high' ? 'bg-orange-100 text-orange-800' : 'bg-yellow-100 text-yellow-800'}`}>
                          {m.priority}
                        </span>
                        <p className="text-xs text-gray-400 mt-1">${(m.estimated_cost / 1000).toFixed(0)}k · {m.timeline_days}d</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </>
          ) : (
            <div className="bg-gray-50 dark:bg-gray-900 rounded-xl p-12 text-center">
              <p className="text-sm text-gray-400">Select suppliers to disrupt and run the simulation to see Monte Carlo results.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
