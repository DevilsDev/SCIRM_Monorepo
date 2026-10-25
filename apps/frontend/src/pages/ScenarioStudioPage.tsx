import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '../contexts/AuthContext';
import { api, Incident, SavedScenario, ScenarioDefinition, ScenarioMitigation, ScenarioResult, ScenarioSupplierRow } from '../services/api';
import { formatTotals } from '../services/money';

const input = 'px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm bg-white dark:bg-gray-800 dark:text-white';
const button = 'px-3 py-1.5 rounded-lg text-sm font-medium disabled:opacity-50';
const card = 'rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-4';

/** One line describing a scenario definition, for the saved list. */
export function describeDefinition(d: ScenarioDefinition): string {
  const who = d.scope.type === 'all' ? 'All suppliers'
    : d.scope.type === 'country' ? `Suppliers in ${(d.scope.country || '').toUpperCase()}`
      : d.scope.type === 'suppliers' ? `${(d.scope.supplier_ids || []).length} supplier(s)`
        : d.scope.type === 'incident' ? 'An incident\'s suppliers' : 'A record\'s suppliers';
  return `${who} out for ${d.duration_weeks} week${d.duration_weeks === 1 ? '' : 's'}`;
}

function errorText(err: any, fallback: string): string {
  const detail = err?.response?.data?.detail;
  return typeof detail === 'string' ? detail : fallback;
}

function SupplierRows({ rows, muted }: { rows: ScenarioSupplierRow[]; muted?: boolean }) {
  return (
    <>
      {rows.map((s) => (
        <tr key={s.supplier_id} className={`border-t border-gray-100 dark:border-gray-700 ${muted ? 'text-gray-500' : 'text-gray-800 dark:text-gray-200'}`}>
          <td className="py-1.5">{s.name}<div className="text-xs text-gray-500">{s.coverage_source}</div></td>
          <td className="text-xs">{s.coverage_weeks ?? '?'} → {s.uncovered_weeks} wk</td>
          <td className="text-xs">{formatTotals(s.at_risk)}</td>
        </tr>
      ))}
    </>
  );
}

function PlanRows({ rows, muted }: { rows: ScenarioMitigation[]; muted?: boolean }) {
  return (
    <>
      {rows.map((m, i) => (
        <li key={`${m.supplier_id}-${m.kind}-${i}`} className={`py-1.5 text-sm ${muted ? 'text-gray-500' : 'text-gray-800 dark:text-gray-200'}`}>
          <span className="font-medium">{m.name}</span>: {m.description}
          <span className="ml-2 text-green-700 dark:text-green-400">−{formatTotals(m.reduction)}</span>
        </li>
      ))}
    </>
  );
}

// Scenario studio and resilience planner: purchase spend at risk if suppliers are out for a
// while, computed by code from SAP spend and the suppliers' own stock answers, and the
// mitigations that would reduce it most. Everyone can run; admins and analysts save.
export default function ScenarioStudioPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const canWrite = !!user?.roles?.some((r) => r === 'admin' || r === 'analyst');
  const [definition, setDefinition] = useState<ScenarioDefinition>({ scope: { type: 'all' }, duration_weeks: 8, second_source_share: 0.5 });
  const [suppliers, setSuppliers] = useState<Array<{ id: string; name: string }>>([]);
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [result, setResult] = useState<ScenarioResult | null>(null);
  const [saved, setSaved] = useState<SavedScenario[]>([]);
  const [name, setName] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const loadSaved = useCallback(() => api.listSavedScenarios().then(setSaved).catch(() => setSaved([])), []);
  useEffect(() => {
    loadSaved();
    api.getSuppliers({ limit: 1000 }).then((r: any) => setSuppliers((r?.suppliers || r || []).map((s: any) => ({ id: s.id, name: s.name }))
      .sort((a: any, b: any) => a.name.localeCompare(b.name)))).catch(() => setSuppliers([]));
    api.listIncidents().then((r) => setIncidents(r.incidents)).catch(() => setIncidents([]));
  }, [loadSaved]);

  const run = async (d: ScenarioDefinition = definition) => {
    setBusy(true); setError('');
    try { setResult(await api.runScenario(d)); } catch (err) { setError(errorText(err, t('sc.runFailed', 'The scenario could not be run.'))); } finally { setBusy(false); }
  };
  const scope = (patch: Partial<ScenarioDefinition['scope']>) => setDefinition((d) => ({ ...d, scope: { ...d.scope, ...patch } }));

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{t('sc.title', 'Scenario studio')}</h1>
      <p className="text-sm text-gray-500 mt-1">{t('sc.subtitle', 'Purchase spend at risk if suppliers are out for a while, and what would reduce it most. Computed from your SAP spend and your suppliers\' own stock answers; nothing is estimated by AI.')}</p>
      <div className="mt-4 grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="space-y-4">
          <div className={card}>
            <label className="text-sm text-gray-700 dark:text-gray-300">{t('sc.who', 'Which suppliers are out')}
              <select value={definition.scope.type} onChange={(e) => scope({ type: e.target.value as ScenarioDefinition['scope']['type'] })} className={`${input} w-full mt-1`}>
                <option value="all">{t('sc.all', 'All suppliers')}</option>
                <option value="country">{t('sc.country', 'Suppliers in a country')}</option>
                <option value="suppliers">{t('sc.pick', 'Chosen suppliers')}</option>
                <option value="incident">{t('sc.incident', "A war-room incident's suppliers")}</option>
              </select>
            </label>
            {definition.scope.type === 'country' && (
              <input value={definition.scope.country || ''} onChange={(e) => scope({ country: e.target.value.toUpperCase() })} maxLength={2}
                placeholder={t('sc.countryCode', 'Country code, e.g. IN')} className={`${input} w-full mt-2`} />
            )}
            {definition.scope.type === 'suppliers' && (
              <select multiple value={definition.scope.supplier_ids || []} onChange={(e) => scope({ supplier_ids: [...e.target.selectedOptions].map((o) => o.value) })}
                className={`${input} w-full mt-2 h-40`} aria-label={t('sc.pick', 'Chosen suppliers')}>
                {suppliers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            )}
            {definition.scope.type === 'incident' && (
              <select value={definition.scope.incident_id || ''} onChange={(e) => scope({ incident_id: e.target.value })} className={`${input} w-full mt-2`} aria-label={t('sc.incident', 'Incident')}>
                <option value="">{t('sc.pickIncident', 'Pick an incident')}</option>
                {incidents.map((i) => <option key={i.id} value={i.id}>{i.title}</option>)}
              </select>
            )}
            <label className="block mt-3 text-sm text-gray-700 dark:text-gray-300">{t('sc.weeks', 'Out for {{n}} weeks', { n: definition.duration_weeks })}
              <input type="range" min={1} max={52} value={definition.duration_weeks} onChange={(e) => setDefinition({ ...definition, duration_weeks: Number(e.target.value) })} className="w-full" />
            </label>
            <p className="mt-3 text-xs font-semibold text-gray-600 dark:text-gray-400">{t('sc.assume', 'Planner assumptions')}</p>
            <label className="block text-xs text-gray-600 dark:text-gray-400">{t('sc.stock', 'Raise safety stock to (weeks)')}
              <input type="number" min={0} max={52} value={definition.stock_target_weeks ?? ''} placeholder={String(definition.duration_weeks)}
                onChange={(e) => setDefinition({ ...definition, stock_target_weeks: e.target.value === '' ? null : Number(e.target.value) })} className={`${input} w-full mt-1`} />
            </label>
            <label className="block mt-2 text-xs text-gray-600 dark:text-gray-400">{t('sc.share', 'Second source takes {{p}}% of volume', { p: Math.round((definition.second_source_share ?? 0.5) * 100) })}
              <input type="range" min={5} max={100} step={5} value={Math.round((definition.second_source_share ?? 0.5) * 100)}
                onChange={(e) => setDefinition({ ...definition, second_source_share: Number(e.target.value) / 100 })} className="w-full" />
            </label>
            <button type="button" disabled={busy} onClick={() => run()} className={`${button} mt-3 bg-blue-600 text-white hover:bg-blue-700`}>{t('sc.run', 'Run scenario')}</button>
            {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
          </div>
          <div className={card}>
            <h2 className="text-sm font-semibold text-gray-900 dark:text-white">{t('sc.saved', 'Saved scenarios')}</h2>
            <ul className="mt-2 divide-y divide-gray-100 dark:divide-gray-700">
              {saved.length === 0 && <li className="py-2 text-sm text-gray-500">{t('sc.noneSaved', 'None yet.')}</li>}
              {saved.map((s) => (
                <li key={s.id} className="py-2 text-sm flex items-center justify-between gap-2">
                  <button type="button" onClick={() => { setDefinition(s.definition); run(s.definition); }} className="text-left text-blue-600 hover:underline">
                    {s.name}<span className="block text-xs text-gray-500">{describeDefinition(s.definition)}</span>
                  </button>
                  {canWrite && <button type="button" onClick={() => api.deleteSavedScenario(s.id).then(loadSaved)} className="text-xs text-red-600 hover:underline">{t('sc.delete', 'Delete')}</button>}
                </li>
              ))}
            </ul>
            {canWrite && (
              <div className="mt-2 flex gap-2">
                <input value={name} onChange={(e) => setName(e.target.value)} maxLength={100} placeholder={t('sc.name', 'Name this scenario')} className={`${input} flex-1 min-w-0`} />
                <button type="button" disabled={!name.trim()} onClick={() => api.saveScenario(name.trim(), definition).then(() => { setName(''); loadSaved(); }).catch((err) => setError(errorText(err, t('sc.saveFailed', 'Could not save.'))))}
                  className={`${button} border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200`}>{t('sc.save', 'Save')}</button>
              </div>
            )}
          </div>
        </div>
        <div className="lg:col-span-2 space-y-4">
          {!result ? <p className="text-sm text-gray-500">{t('sc.hint', 'Choose who is out and for how long, then run the scenario.')}</p> : (
            <>
              <div className={card}>
                <p className="text-xs text-gray-500">{result.scope} · {t('sc.out', '{{n}} weeks', { n: result.duration_weeks })} · {t('sc.count', '{{n}} supplier(s)', { n: result.supplier_count })}</p>
                <div className="mt-2 grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div><p className="text-xs text-gray-500">{t('sc.interrupted', 'Purchase flow interrupted')}</p><p className="text-lg font-semibold text-gray-900 dark:text-white">{formatTotals(result.interrupted)}</p></div>
                  <div><p className="text-xs text-gray-500">{t('sc.atRisk', 'Not covered by stated safety stock (at risk)')}</p><p className="text-lg font-semibold text-red-700 dark:text-red-400">{formatTotals(result.at_risk)}</p></div>
                </div>
                {result.suppliers_without_coverage_data > 0 && (
                  <p className="mt-2 text-xs text-amber-700 dark:text-amber-300">{t('sc.unknown', '{{n}} supplier(s) have not stated their safety stock: counted as 0 weeks. Send them the supply continuity questionnaire.', { n: result.suppliers_without_coverage_data })}</p>
                )}
              </div>
              <div className={card}>
                <h2 className="text-sm font-semibold text-gray-900 dark:text-white">{t('sc.plan', 'Resilience plan: what reduces spend at risk most')}{result.main_currency ? ` (${result.main_currency})` : ''}</h2>
                <ol className="mt-2 list-decimal ml-5"><PlanRows rows={result.plan.ranked} /></ol>
                {result.plan.other_currencies.length > 0 && (
                  <><p className="mt-2 text-xs text-gray-500">{t('sc.otherCurrencies', 'In other currencies (not ranked):')}</p><ul className="ml-5"><PlanRows rows={result.plan.other_currencies} muted /></ul></>
                )}
                {result.plan.ranked.length + result.plan.other_currencies.length === 0 && <p className="text-sm text-gray-500">{t('sc.nothing', 'Nothing is at risk in this scenario.')}</p>}
              </div>
              <div className={card}>
                <h2 className="text-sm font-semibold text-gray-900 dark:text-white">{t('sc.bySupplier', 'By supplier')}</h2>
                <table className="mt-2 w-full text-sm"><tbody>
                  <SupplierRows rows={result.suppliers.ranked} />
                  <SupplierRows rows={result.suppliers.other_currencies} muted />
                </tbody></table>
              </div>
              <div className={card}>
                <h2 className="text-sm font-semibold text-gray-900 dark:text-white">{t('sc.assumptions', 'How this is computed')}</h2>
                <ul className="mt-2 list-disc ml-5 text-sm text-gray-700 dark:text-gray-300">{result.assumptions.map((a) => <li key={a}>{a}</li>)}</ul>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
