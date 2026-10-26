import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAuth } from '../contexts/AuthContext';
import {
  api, DdCatalog, DdEffectiveness, DdMeasureStatus, DdOverviewRow, DdReview, DdRiskStatus, DdSupplierView,
} from '../services/api';
import { utcDate } from '../services/time';
import { formatTotals } from '../services/money';

const input = 'px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm bg-white dark:bg-gray-800 dark:text-white';
const button = 'px-3 py-1.5 rounded-lg text-sm font-medium disabled:opacity-50';
const card = 'rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-4';
const primary = `${button} bg-blue-600 text-white hover:bg-blue-700`;

export const REVIEW_LABEL: Record<DdReview['state'], string> = {
  not_analysed: 'Not analysed', current: 'Analysis current', suggested: 'Review suggested', due: 'Review due',
};
const REVIEW_STYLE: Record<DdReview['state'], string> = {
  not_analysed: 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-200',
  current: 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-200',
  suggested: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200',
  due: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-200',
};
const MEASURE_STATUS_LABEL: Record<DdMeasureStatus, string> = {
  planned: 'Planned', in_progress: 'In progress', done: 'Done', cancelled: 'Cancelled',
};
const EFFECTIVENESS_LABEL: Record<DdEffectiveness, string> = {
  not_reviewed: 'Effectiveness not reviewed', effective: 'Effective', partly_effective: 'Partly effective',
  not_effective: 'Not effective',
};
const RISK_STATUS_LABEL: Record<DdRiskStatus, string> = { open: 'Open', mitigated: 'Mitigated', closed: 'Closed' };

/** "Severity high, likelihood possible": severity first, as risks are prioritised. */
export function ratingText(catalog: Pick<DdCatalog, 'likelihood' | 'severity'>, likelihood: number, severity: number): string {
  return `Severity ${(catalog.severity[String(severity)] || '?').toLowerCase()}, likelihood ${(catalog.likelihood[String(likelihood)] || '?').toLowerCase()}`;
}

/** Suppliers that need attention first: review due, suggested, never analysed, then by open risks. */
export function attentionOrder(rows: DdOverviewRow[]): DdOverviewRow[] {
  const rank: Record<DdReview['state'], number> = { due: 0, suggested: 1, not_analysed: 2, current: 3 };
  return [...rows].sort((a, b) => rank[a.review.state] - rank[b.review.state]
    || (b.top_risk?.severity || 0) - (a.top_risk?.severity || 0) || b.open_risks - a.open_risks
    || a.name.localeCompare(b.name));
}

function errorText(err: any, fallback: string): string {
  const detail = err?.response?.data?.detail;
  return typeof detail === 'string' ? detail : fallback;
}

function ReviewBadge({ review }: { review: DdReview }) {
  return <span className={`text-xs px-2 py-0.5 rounded-full whitespace-nowrap ${REVIEW_STYLE[review.state]}`}>{REVIEW_LABEL[review.state]}</span>;
}

function RiskForm({ catalog, supplierId, onDone }: { catalog: DdCatalog; supplierId: string; onDone: () => void }) {
  const { t } = useTranslation();
  const [f, setF] = useState({ area: catalog.areas[0].key, description: '', likelihood: 2, severity: 2, rating_reason: '', source: 'scoping', source_ref: '' });
  const [error, setError] = useState('');
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    try {
      await api.ddAddRisk({ ...f, supplier_id: supplierId, source_ref: f.source_ref || null });
      setF({ ...f, description: '', rating_reason: '', source_ref: '' });
      onDone();
    } catch (err) { setError(errorText(err, t('dd.failed', 'That did not work.'))); }
  };
  const area = catalog.areas.find((a) => a.key === f.area);
  return (
    <form onSubmit={submit} className="mt-3 space-y-2 border-t border-gray-100 dark:border-gray-700 pt-3">
      <select value={f.area} onChange={(e) => setF({ ...f, area: e.target.value })} className={`${input} w-full`} aria-label={t('dd.area', 'Risk area')}>
        {(['human_rights', 'environment'] as const).map((g) => (
          <optgroup key={g} label={g === 'human_rights' ? 'Human rights' : 'Environment'}>
            {catalog.areas.filter((a) => a.group === g).map((a) => <option key={a.key} value={a.key}>{a.label}</option>)}
          </optgroup>
        ))}
      </select>
      {area && <p className="text-xs text-gray-500">{[area.lksg && `LkSG ${area.lksg}`, `CSDDD ${area.csddd}`].filter(Boolean).join(' · ')}</p>}
      <textarea required rows={2} maxLength={2000} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} placeholder={t('dd.riskDescription', 'What is the risk, where?')} className={`${input} w-full`} />
      <div className="flex flex-wrap gap-2">
        <select value={f.severity} onChange={(e) => setF({ ...f, severity: Number(e.target.value) })} className={input} aria-label={t('dd.severity', 'Severity')}>
          {Object.entries(catalog.severity).map(([k, v]) => <option key={k} value={k}>Severity: {v}</option>)}
        </select>
        <select value={f.likelihood} onChange={(e) => setF({ ...f, likelihood: Number(e.target.value) })} className={input} aria-label={t('dd.likelihood', 'Likelihood')}>
          {Object.entries(catalog.likelihood).map(([k, v]) => <option key={k} value={k}>Likelihood: {v}</option>)}
        </select>
        <select value={f.source} onChange={(e) => setF({ ...f, source: e.target.value })} className={input} aria-label={t('dd.source', 'Source')}>
          {catalog.sources.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
        </select>
      </div>
      <input required maxLength={2000} value={f.rating_reason} onChange={(e) => setF({ ...f, rating_reason: e.target.value })} placeholder={t('dd.ratingReason', 'Why this rating? (required)')} className={`${input} w-full`} />
      <input maxLength={200} value={f.source_ref} onChange={(e) => setF({ ...f, source_ref: e.target.value })} placeholder={t('dd.sourceRef', 'Reference (optional): report, record or questionnaire')} className={`${input} w-full`} />
      {error && <p className="text-sm text-red-600">{error}</p>}
      <button type="submit" className={primary}>{t('dd.addRisk', 'Record risk')}</button>
    </form>
  );
}

function MeasureForm({ catalog, view, members, onDone }: { catalog: DdCatalog; view: DdSupplierView; members: string[]; onDone: () => void }) {
  const { t } = useTranslation();
  const [f, setF] = useState({ risk_id: '', kind: 'corrective_action_plan', description: '', owner_email: '', due_date: '' });
  const [error, setError] = useState('');
  const kind = catalog.measure_kinds.find((k) => k.key === f.kind);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    try {
      await api.ddAddMeasure({ supplier_id: view.supplier.id, kind: f.kind, description: f.description,
        risk_id: f.risk_id || null, owner_email: f.owner_email || null, due_date: f.due_date || null });
      setF({ ...f, description: '' });
      onDone();
    } catch (err) { setError(errorText(err, t('dd.failed', 'That did not work.'))); }
  };
  return (
    <form onSubmit={submit} className="mt-3 space-y-2 border-t border-gray-100 dark:border-gray-700 pt-3">
      <div className="flex flex-wrap gap-2">
        <select value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })} className={input} aria-label={t('dd.kind', 'Kind of measure')}>
          {catalog.measure_kinds.map((k) => <option key={k.key} value={k.key}>{k.label}</option>)}
        </select>
        <select value={f.risk_id} onChange={(e) => setF({ ...f, risk_id: e.target.value })} className={`${input} flex-1 min-w-[160px]`} aria-label={t('dd.forRisk', 'For risk')}>
          <option value="">{t('dd.noRisk', 'Not tied to one risk')}</option>
          {view.risks.filter((r) => r.status !== 'closed').map((r) => (
            <option key={r.id} value={r.id}>{catalog.areas.find((a) => a.key === r.area)?.label}: {r.description.slice(0, 50)}</option>
          ))}
        </select>
      </div>
      {kind?.last_resort && (
        <p className="text-xs text-amber-700 dark:text-amber-300">
          {t('dd.lastResort', 'A last resort: for impacts that prevention and mitigation could not address (CSDDD Article 10(6), LkSG § 7(3)). Weigh the effect on the people concerned before acting.')}
        </p>
      )}
      <textarea required rows={2} maxLength={2000} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} placeholder={t('dd.measureDescription', 'What will be done?')} className={`${input} w-full`} />
      <div className="flex flex-wrap gap-2">
        {members.length > 0 ? (
          <select value={f.owner_email} onChange={(e) => setF({ ...f, owner_email: e.target.value })} className={input} aria-label={t('dd.owner', 'Owner')}>
            <option value="">{t('dd.noOwner', 'No owner')}</option>
            {members.map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
        ) : (
          <input type="email" maxLength={254} value={f.owner_email} onChange={(e) => setF({ ...f, owner_email: e.target.value })} placeholder={t('dd.ownerEmail', 'Owner email (a member)')} className={input} />
        )}
        <input type="date" value={f.due_date} onChange={(e) => setF({ ...f, due_date: e.target.value })} className={input} aria-label={t('dd.due', 'Due date')} />
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}
      <button type="submit" className={primary}>{t('dd.addMeasure', 'Add measure')}</button>
    </form>
  );
}

function Detail({ id, catalog, canWrite, members, onChanged }: { id: string; catalog: DdCatalog; canWrite: boolean; members: string[]; onChanged: () => void }) {
  const { t } = useTranslation();
  const [view, setView] = useState<DdSupplierView | null>(null);
  const [rerate, setRerate] = useState<{ id: string; likelihood: number; severity: number; reason: string } | null>(null);
  const [effect, setEffect] = useState<Record<string, string>>({});
  const [conclusion, setConclusion] = useState('');
  const [error, setError] = useState('');
  const load = useCallback(() => api.ddSupplier(id).then(setView)
    .catch((err) => setError(errorText(err, t('dd.loadFailed', 'Could not load the supplier.')))), [id, t]);
  useEffect(() => { load(); }, [load]);
  const act = async (fn: () => Promise<unknown>) => {
    setError('');
    try { await fn(); await load(); onChanged(); } catch (err) { setError(errorText(err, t('dd.failed', 'That did not work.'))); }
  };
  const areaOf = useMemo(() => Object.fromEntries(catalog.areas.map((a) => [a.key, a])), [catalog]);
  const kindOf = useMemo(() => Object.fromEntries(catalog.measure_kinds.map((k) => [k.key, k])), [catalog]);
  const sourceOf = useMemo(() => Object.fromEntries(catalog.sources.map((s) => [s.key, s.label])), [catalog]);
  if (!view) return error ? <p className="text-sm text-red-600">{error}</p> : null;
  const r = view.review;

  return (
    <div className="space-y-4">
      <div className={card}>
        <div className="flex flex-wrap items-start justify-between gap-2">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">{view.supplier.name}</h2>
          <ReviewBadge review={r} />
        </div>
        <p className="text-xs text-gray-500 mt-1">
          {r.last_review
            ? t('dd.lastReview', 'Risk analysis last reviewed {{at}}; next by {{next}}.', { at: utcDate(r.last_review).toLocaleDateString(), next: utcDate(r.next_review as string).toLocaleDateString() })
            : t('dd.neverReviewed', 'No risk analysis recorded yet.')}
        </p>
        {r.reasons.length > 0 && (
          <ul className="mt-1 text-xs text-amber-700 dark:text-amber-300 list-disc pl-4">
            {r.reasons.map((x) => <li key={x}>{t('dd.since', 'Since the last review: {{x}}', { x })}</li>)}
          </ul>
        )}
        {canWrite && (
          <form onSubmit={(e) => { e.preventDefault(); act(() => api.ddReview(view.supplier.id, conclusion)).then(() => setConclusion('')); }} className="mt-3 flex flex-wrap gap-2">
            <input required maxLength={4000} value={conclusion} onChange={(e) => setConclusion(e.target.value)} placeholder={t('dd.conclusion', 'Conclusions of this review of the risk analysis')} className={`${input} flex-1 min-w-[200px]`} />
            <button type="submit" className={primary}>{t('dd.recordReview', 'Record review')}</button>
          </form>
        )}
        {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
      </div>

      <div className={card}>
        <h3 className="text-sm font-semibold text-gray-900 dark:text-white">{t('dd.holds', 'What SCIRM already holds')}</h3>
        <ul className="mt-1 text-sm text-gray-700 dark:text-gray-300 space-y-1">
          {view.facts.length === 0 && view.assessments.length === 0 && <li className="text-gray-500">{t('dd.nothingYet', 'No incidents or questionnaires for this supplier.')}</li>}
          {view.facts.map((f) => <li key={f.at + f.text}>{utcDate(f.at).toLocaleDateString()} · {f.text}</li>)}
          {view.assessments.filter((a) => a.status === 'sent').map((a) => <li key={a.id}>{t('dd.waiting', 'Waiting for answers: {{n}}', { n: a.template_name })}</li>)}
          {view.assessments.filter((a) => a.flags.length > 0 && a.status !== 'cancelled').map((a) => (
            <li key={`f-${a.id}`} className="text-amber-700 dark:text-amber-300">
              {t('dd.flags', '{{n}}: {{c}} answer(s) to follow up (supplier-provided)', { n: a.template_name, c: a.flags.length })}
            </li>
          ))}
        </ul>
        {canWrite && (
          <p className="mt-2 text-xs text-gray-500">
            {t('dd.askHint', 'Need the supplier’s own information? Send the "Human rights and environment" questionnaire from')}{' '}
            <Link to="/supplier-assessments" className="text-blue-600 hover:underline">{t('nav.supplierAssessments', 'Supplier assessments')}</Link>
            {t('dd.askHint2', ', with the reason it is needed.')}
          </p>
        )}
      </div>

      <div className={card}>
        <h3 className="text-sm font-semibold text-gray-900 dark:text-white">{t('dd.risks', 'Risks')}</h3>
        <p className="text-xs text-gray-500">{t('dd.risksHint', 'Rated by people, most severe first. SCIRM does not score suppliers, countries or sectors.')}</p>
        {view.risks.length === 0 && <p className="mt-2 text-sm text-gray-500">{t('dd.noRisks', 'No risks recorded.')}</p>}
        <ul className="mt-2 space-y-3">
          {view.risks.map((risk) => (
            <li key={risk.id} className={`text-sm ${risk.status === 'closed' ? 'opacity-60' : ''}`}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-medium text-gray-900 dark:text-white">{areaOf[risk.area]?.label}</span>
                <span className="text-xs text-gray-500">{RISK_STATUS_LABEL[risk.status]}</span>
              </div>
              <p className="text-gray-700 dark:text-gray-300">{risk.description}</p>
              <p className="text-xs text-gray-500">
                {ratingText(catalog, risk.likelihood, risk.severity)} · {risk.rating_reason} · {sourceOf[risk.source]}
                {risk.source_ref ? ` (${risk.source_ref})` : ''} · {risk.assessed_by || '-'}, {utcDate(risk.assessed_at).toLocaleDateString()}
              </p>
              {canWrite && (
                <div className="mt-1 flex flex-wrap gap-2 text-xs">
                  <select value={risk.status} onChange={(e) => act(() => api.ddUpdateRisk(risk.id, { status: e.target.value as DdRiskStatus }))} className={input} aria-label={t('dd.riskStatus', 'Risk status')}>
                    {catalog.risk_statuses.map((s) => <option key={s} value={s}>{RISK_STATUS_LABEL[s]}</option>)}
                  </select>
                  {rerate?.id === risk.id ? (
                    <form onSubmit={(e) => { e.preventDefault(); act(() => api.ddUpdateRisk(risk.id, { likelihood: rerate.likelihood, severity: rerate.severity, rating_reason: rerate.reason })).then(() => setRerate(null)); }} className="flex flex-wrap gap-2">
                      <select value={rerate.severity} onChange={(e) => setRerate({ ...rerate, severity: Number(e.target.value) })} className={input} aria-label={t('dd.severity', 'Severity')}>
                        {Object.entries(catalog.severity).map(([k, v]) => <option key={k} value={k}>Severity: {v}</option>)}
                      </select>
                      <select value={rerate.likelihood} onChange={(e) => setRerate({ ...rerate, likelihood: Number(e.target.value) })} className={input} aria-label={t('dd.likelihood', 'Likelihood')}>
                        {Object.entries(catalog.likelihood).map(([k, v]) => <option key={k} value={k}>Likelihood: {v}</option>)}
                      </select>
                      <input required maxLength={2000} value={rerate.reason} onChange={(e) => setRerate({ ...rerate, reason: e.target.value })} placeholder={t('dd.ratingReason', 'Why this rating? (required)')} className={input} />
                      <button type="submit" className={primary}>{t('dd.save', 'Save')}</button>
                      <button type="button" onClick={() => setRerate(null)} className={`${button} text-gray-600 dark:text-gray-300`}>{t('common.cancel', 'Cancel')}</button>
                    </form>
                  ) : (
                    <button type="button" onClick={() => setRerate({ id: risk.id, likelihood: risk.likelihood, severity: risk.severity, reason: '' })} className="text-blue-600 hover:underline">{t('dd.rerate', 'Re-rate')}</button>
                  )}
                </div>
              )}
            </li>
          ))}
        </ul>
        {canWrite && <RiskForm catalog={catalog} supplierId={view.supplier.id} onDone={() => { load(); onChanged(); }} />}
      </div>

      <div className={card}>
        <h3 className="text-sm font-semibold text-gray-900 dark:text-white">{t('dd.measures', 'Measures')}</h3>
        {view.measures.length === 0 && <p className="mt-2 text-sm text-gray-500">{t('dd.noMeasures', 'No measures yet.')}</p>}
        <ul className="mt-2 space-y-3">
          {view.measures.map((m) => (
            <li key={m.id} className="text-sm">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-medium text-gray-900 dark:text-white">
                  {kindOf[m.kind]?.label}
                  {kindOf[m.kind]?.last_resort && <span className="ml-2 text-xs text-amber-700 dark:text-amber-300">{t('dd.lastResortTag', 'last resort')}</span>}
                </span>
                <span className="text-xs text-gray-500">{MEASURE_STATUS_LABEL[m.status]} · {EFFECTIVENESS_LABEL[m.effectiveness]}</span>
              </div>
              <p className="text-gray-700 dark:text-gray-300">{m.description}</p>
              <p className="text-xs text-gray-500">
                {m.owner_email || t('dd.noOwner', 'No owner')}{m.due_date ? ` · ${t('dd.dueBy', 'due {{d}}', { d: m.due_date })}` : ''}
                {m.risk_id ? ` · ${areaOf[view.risks.find((x) => x.id === m.risk_id)?.area || '']?.label || ''}` : ''}
                {m.effectiveness_note ? ` · ${m.effectiveness_note}` : ''}
              </p>
              {canWrite && (
                <div className="mt-1 flex flex-wrap gap-2 text-xs">
                  <select value={m.status} onChange={(e) => act(() => api.ddUpdateMeasure(m.id, { status: e.target.value as DdMeasureStatus }))} className={input} aria-label={t('dd.measureStatus', 'Measure status')}>
                    {catalog.measure_statuses.map((s) => <option key={s} value={s}>{MEASURE_STATUS_LABEL[s]}</option>)}
                  </select>
                  <select value={m.effectiveness} onChange={(e) => act(() => api.ddUpdateMeasure(m.id, { effectiveness: e.target.value as DdEffectiveness, effectiveness_note: effect[m.id] || null }))} className={input} aria-label={t('dd.effectiveness', 'Effectiveness')}>
                    {catalog.effectiveness.map((s) => <option key={s} value={s}>{EFFECTIVENESS_LABEL[s]}</option>)}
                  </select>
                  <input maxLength={2000} value={effect[m.id] || ''} onChange={(e) => setEffect({ ...effect, [m.id]: e.target.value })} placeholder={t('dd.effectNote', 'How was it checked? (note, before choosing)')} className={`${input} flex-1 min-w-[160px]`} />
                </div>
              )}
            </li>
          ))}
        </ul>
        {canWrite && <MeasureForm catalog={catalog} view={view} members={members} onDone={() => { load(); onChanged(); }} />}
      </div>

      <div className={card}>
        <h3 className="text-sm font-semibold text-gray-900 dark:text-white">{t('dd.history', 'History')}</h3>
        <p className="text-xs text-gray-500">{t('dd.historyHint', 'Kept, never edited or deleted (LkSG § 10(1): seven years).')}</p>
        <ol className="mt-2 space-y-2">
          {[...view.history].reverse().map((e) => (
            <li key={e.id} className="text-sm">
              <span className="text-xs text-gray-500">{utcDate(e.created_at).toLocaleString()} · {e.actor || '-'}</span>
              <p className={e.kind === 'analysis_reviewed' ? 'text-gray-900 dark:text-white' : 'text-gray-600 dark:text-gray-400'}>
                {e.kind === 'analysis_reviewed' ? `${t('dd.reviewed', 'Risk analysis reviewed')}: ` : ''}{e.text}
              </p>
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}

// Human rights and environmental due diligence (LkSG, CSDDD): a scoping view of every active
// supplier from what SCIRM already holds, then per supplier the risks people rated, the
// measures and their effectiveness, the periodic review and the full history.
export default function DueDiligencePage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const canWrite = !!user?.roles?.some((r) => r === 'admin' || r === 'analyst');
  const isAdmin = !!user?.roles?.includes('admin');
  const [params, setParams] = useSearchParams();
  const selected = params.get('supplier');
  const [catalog, setCatalog] = useState<DdCatalog | null>(null);
  const [rows, setRows] = useState<DdOverviewRow[]>([]);
  const [months, setMonths] = useState(12);
  const [members, setMembers] = useState<string[]>([]);
  const [attention, setAttention] = useState(false);
  const [year, setYear] = useState(new Date().getFullYear());
  const [notice, setNotice] = useState('');

  const load = useCallback(() => api.ddOverview().then((r) => { setRows(r.suppliers); setMonths(r.settings.review_months); })
    .catch(() => setRows([])), []);
  useEffect(() => {
    load();
    api.ddCatalog().then(setCatalog).catch(() => setCatalog(null));
    api.listMembers().then((r) => setMembers(r.members.filter((m) => m.is_active).map((m) => m.email))).catch(() => setMembers([]));
  }, [load]);

  const shown = attentionOrder(rows).filter((r) => !attention || r.review.state !== 'current' || r.open_risks > 0);
  const download = async (format: 'json' | 'csv') => {
    setNotice('');
    try {
      const url = URL.createObjectURL(await api.ddExport(year, format));
      const a = document.createElement('a');
      a.href = url;
      a.download = `scirm-due-diligence-${year}.${format}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch { setNotice(t('dd.exportFailed', 'The documentation could not be downloaded.')); }
  };
  const saveMonths = async (value: number) => {
    setNotice('');
    try { setMonths((await api.ddSetReviewMonths(value)).review_months); load(); } catch (err) { setNotice(errorText(err, t('dd.failed', 'That did not work.'))); }
  };

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{t('dd.title', 'Due diligence')}</h1>
          <p className="text-sm text-gray-500">{t('dd.subtitle', 'Human rights and environmental risks in your supply chain (LkSG, CSDDD): rated risks, measures, reviews and the yearly documentation.')}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <select value={year} onChange={(e) => setYear(Number(e.target.value))} className={input} aria-label={t('dd.year', 'Year')}>
            {[0, 1, 2, 3, 4, 5, 6].map((d) => new Date().getFullYear() - d).map((y) => <option key={y} value={y}>{y}</option>)}
          </select>
          <button type="button" onClick={() => download('json')} className={`${button} border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200`}>{t('dd.exportJson', 'Documentation (JSON)')}</button>
          <button type="button" onClick={() => download('csv')} className={`${button} border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200`}>{t('dd.exportCsv', 'History (CSV)')}</button>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-3 mb-3 text-sm text-gray-600 dark:text-gray-400">
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={attention} onChange={(e) => setAttention(e.target.checked)} />
          {t('dd.attention', 'Only suppliers that need attention')}
        </label>
        <span>
          {t('dd.interval', 'Review each risk analysis every')}{' '}
          {isAdmin ? (
            <select value={months} onChange={(e) => saveMonths(Number(e.target.value))} className={input} aria-label={t('dd.months', 'Months')}>
              {[3, 6, 12, 24, 36, 60].map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
          ) : months}{' '}
          {t('dd.monthsAnd', 'months, and after a significant change.')}
        </span>
        {notice && <span className="text-red-600">{notice}</span>}
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        <div className="lg:col-span-2">
          <ul className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 divide-y divide-gray-100 dark:divide-gray-700">
            {shown.length === 0 && <li className="p-4 text-sm text-gray-500">{t('dd.noSuppliers', 'No suppliers to show.')}</li>}
            {shown.map((s) => (
              <li key={s.supplier_id} onClick={() => setParams({ supplier: s.supplier_id })} className={`p-3 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700/40 ${selected === s.supplier_id ? 'bg-blue-50 dark:bg-blue-900/20' : ''}`}>
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-medium text-gray-900 dark:text-white">{s.name}</span>
                  <ReviewBadge review={s.review} />
                </div>
                <p className="text-xs text-gray-500 mt-1">
                  {[s.country_code, ...s.site_countries.filter((c) => c !== s.country_code)].filter(Boolean).join(', ') || t('dd.noCountry', 'No country')}
                  {s.spend_12m && Object.keys(s.spend_12m).length > 0 ? ` · ${formatTotals(s.spend_12m)}` : ''}
                  {s.incidents ? ` · ${t('dd.incidents', '{{n}} incident(s)', { n: s.incidents })}` : ''}
                </p>
                <p className="text-xs text-gray-500">
                  {s.open_risks
                    ? t('dd.openRisks', '{{n}} open risk(s), most severe: {{a}}', { n: s.open_risks, a: catalog?.areas.find((a) => a.key === s.top_risk?.area)?.label || s.top_risk?.area })
                    : t('dd.noOpenRisks', 'No open risks recorded')}
                  {s.open_measures ? ` · ${t('dd.openMeasures', '{{n}} measure(s) under way', { n: s.open_measures })}` : ''}
                </p>
              </li>
            ))}
          </ul>
        </div>
        <div className="lg:col-span-3">
          {selected && catalog ? <Detail key={selected} id={selected} catalog={catalog} canWrite={canWrite} members={members} onChanged={load} />
            : <p className="text-sm text-gray-500">{t('dd.pick', 'Pick a supplier.')}</p>}
        </div>
      </div>
    </div>
  );
}
