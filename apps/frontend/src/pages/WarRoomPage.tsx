import { FormEvent, useCallback, useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAuth } from '../contexts/AuthContext';
import { api, Incident, IncidentDetail, IncidentSeverity, IncidentStatus } from '../services/api';
import SeverityBadge from '../components/SeverityBadge';
import { utcDate } from '../services/time';
import { formatMoney } from '../services/money';
import SignaturePanel from '../components/SignaturePanel';

const input = 'px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm bg-white dark:bg-gray-800 dark:text-white';
const button = 'px-3 py-1.5 rounded-lg text-sm font-medium disabled:opacity-50';
const card = 'rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-4';
const POLL_MS = 30000;

const STATUS_LABEL: Record<IncidentStatus, string> = { open: 'Open', monitoring: 'Monitoring', resolved: 'Resolved' };
const STATUS_STYLE: Record<IncidentStatus, string> = {
  open: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-200',
  monitoring: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200',
  resolved: 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-200',
};
const SEVERITIES: IncidentSeverity[] = ['low', 'medium', 'high', 'critical'];

export { formatMoney };

function errorText(err: any, fallback: string): string {
  const detail = err?.response?.data?.detail;
  return typeof detail === 'string' ? detail : fallback;
}

function OpenForm({ onOpened }: { onOpened: (d: IncidentDetail) => void }) {
  const { t } = useTranslation();
  const [title, setTitle] = useState('');
  const [summary, setSummary] = useState('');
  const [severity, setSeverity] = useState<IncidentSeverity>('medium');
  const [error, setError] = useState('');
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    try {
      onOpened(await api.openIncident({ title, summary, severity }));
      setTitle(''); setSummary('');
    } catch (err) { setError(errorText(err, t('wr.openFailed', 'The incident could not be opened.'))); }
  };
  return (
    <form onSubmit={submit} className={`${card} mb-4 space-y-2`}>
      <div className="flex gap-2">
        <input required maxLength={200} value={title} onChange={(e) => setTitle(e.target.value)} placeholder={t('wr.titlePlaceholder', 'What is happening? e.g. Port strike in Rotterdam')} className={`${input} flex-1`} />
        <select value={severity} onChange={(e) => setSeverity(e.target.value as IncidentSeverity)} className={input} aria-label={t('wr.severity', 'Severity')}>
          {SEVERITIES.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>
      <textarea rows={2} maxLength={4000} value={summary} onChange={(e) => setSummary(e.target.value)} placeholder={t('wr.summaryPlaceholder', 'Summary (optional)')} className={`${input} w-full`} />
      {error && <p className="text-sm text-red-600">{error}</p>}
      <button type="submit" className={`${button} bg-blue-600 text-white hover:bg-blue-700`}>{t('wr.open', 'Open incident')}</button>
    </form>
  );
}

function Detail({ id, members, canWrite, onChanged }: { id: string; members: string[]; canWrite: boolean; onChanged: () => void }) {
  const { t } = useTranslation();
  const [data, setData] = useState<IncidentDetail | null>(null);
  const [suppliers, setSuppliers] = useState<Array<{ id: string; name: string }>>([]);
  const [note, setNote] = useState('');
  const [task, setTask] = useState({ title: '', assignee_email: '', due_date: '' });
  const [addSupplier, setAddSupplier] = useState('');
  const [resolution, setResolution] = useState('');
  const [error, setError] = useState('');

  const load = useCallback(() => api.getIncident(id).then(setData)
    .catch((err) => setError(errorText(err, t('wr.loadFailed', 'Could not load the incident.')))), [id, t]);
  useEffect(() => {
    load();
    const timer = window.setInterval(load, POLL_MS);  // others may be working on it too
    return () => window.clearInterval(timer);
  }, [load]);
  useEffect(() => {
    if (!canWrite) return;
    api.getSuppliers({ limit: 1000 }).then((r: any) => setSuppliers((r?.suppliers || r || [])
      .map((s: any) => ({ id: s.id, name: s.name })).sort((a: any, b: any) => a.name.localeCompare(b.name))))
      .catch(() => setSuppliers([]));
  }, [canWrite]);

  const act = async (fn: () => Promise<IncidentDetail>) => {
    setError('');
    try { setData(await fn()); onChanged(); } catch (err) { setError(errorText(err, t('wr.actionFailed', 'That did not work.'))); }
  };
  if (!data) return error ? <p className="text-sm text-red-600">{error}</p> : null;
  const i = data.incident;
  const linked = new Set(data.suppliers.map((s) => s.id));
  const currencies = Object.entries(data.exposure.by_currency);
  return (
    <div className="space-y-4">
      <div className={card}>
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">{i.title}</h2>
            <p className="text-xs text-gray-500">{t('wr.openedBy', 'Opened by {{by}}, {{at}}', { by: i.opened_by || '-', at: utcDate(i.created_at).toLocaleString() })}</p>
          </div>
          <span className={`text-xs px-2 py-1 rounded-full ${STATUS_STYLE[i.status]}`}>{STATUS_LABEL[i.status]}</span>
        </div>
        {i.summary && <p className="mt-2 text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap">{i.summary}</p>}
        {i.signal && (
          <p className="mt-2 text-xs text-gray-600 dark:text-gray-400">
            {t('wr.fromRecord', 'From {{source}}:', { source: i.signal.source_label || i.signal.source })}{' '}
            {i.signal.url ? <a href={i.signal.url} target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline">{i.signal.title}</a> : i.signal.title}
            {' '}({i.signal.published_at})
          </p>
        )}
        <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
          <SeverityBadge severity={i.severity} />
          {canWrite ? (
            <>
              <select value={i.severity} onChange={(e) => act(() => api.updateIncident(i.id, { severity: e.target.value as IncidentSeverity }))} className={input} aria-label={t('wr.severity', 'Severity')}>
                {SEVERITIES.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
              <select value={i.owner_email || ''} onChange={(e) => act(() => api.updateIncident(i.id, { owner_email: e.target.value || null }))} className={input} aria-label={t('wr.owner', 'Owner')}>
                <option value="">{t('wr.noOwner', 'No owner')}</option>
                {members.map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
              {i.status !== 'resolved' ? (
                <>
                  {i.status === 'open'
                    ? <button type="button" onClick={() => act(() => api.updateIncident(i.id, { status: 'monitoring' }))} className={`${button} border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200`}>{t('wr.monitor', 'Monitoring')}</button>
                    : <button type="button" onClick={() => act(() => api.updateIncident(i.id, { status: 'open' }))} className={`${button} border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200`}>{t('wr.reopen', 'Back to open')}</button>}
                  <input value={resolution} onChange={(e) => setResolution(e.target.value)} maxLength={4000} placeholder={t('wr.resolution', 'Resolution (optional)')} className={`${input} min-w-[180px]`} />
                  <button type="button" onClick={() => act(() => api.updateIncident(i.id, { status: 'resolved', ...(resolution ? { resolution } : {}) }))} className={`${button} bg-green-600 text-white hover:bg-green-700`}>{t('wr.resolve', 'Resolve')}</button>
                </>
              ) : (
                <button type="button" onClick={() => act(() => api.updateIncident(i.id, { status: 'open' }))} className={`${button} border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200`}>{t('wr.reopenResolved', 'Reopen')}</button>
              )}
            </>
          ) : (
            <span className="text-gray-600 dark:text-gray-400">{t('wr.ownerIs', 'Owner: {{o}}', { o: i.owner_email || '-' })}</span>
          )}
        </div>
        {i.resolution && <p className="mt-2 text-sm text-gray-700 dark:text-gray-300">{t('wr.resolvedWith', 'Resolution: {{r}}', { r: i.resolution })}</p>}
        <SignaturePanel key={i.id} recordType="incident" recordId={i.id} meanings={['approved', 'reviewed', 'responsible']} />
        {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
      </div>

      <div className={card}>
        <h3 className="text-sm font-semibold text-gray-900 dark:text-white">{t('wr.suppliers', 'Affected suppliers')}</h3>
        <p className="mt-1 text-sm text-gray-700 dark:text-gray-300">
          {t('wr.exposure', '12-month spend at stake:')}{' '}
          {currencies.length ? currencies.map(([c, v]) => formatMoney(v, c)).join(' + ') : t('wr.noSpend', 'no spend data')}
          {data.exposure.without_spend > 0 && <span className="text-xs text-gray-500"> {t('wr.withoutSpend', '({{n}} without spend data)', { n: data.exposure.without_spend })}</span>}
        </p>
        <p className="text-xs text-gray-500">{t('wr.perCurrency', 'Totals are per currency; they are never converted or added together.')}</p>
        <table className="mt-2 w-full text-sm">
          <tbody>
            {data.suppliers.map((s) => (
              <tr key={s.id} className="border-t border-gray-100 dark:border-gray-700 text-gray-800 dark:text-gray-200">
                <td className="py-1.5">{s.name}<div className="text-xs text-gray-500">{s.reason}</div></td>
                <td className="text-xs">{s.country_code || ''}</td>
                <td className="text-xs">{Object.entries(s.spend_12m || {}).map(([c, v]) => formatMoney(v, c)).join(', ') || '-'}</td>
                <td className="text-right">{canWrite && <button type="button" onClick={() => act(() => api.removeIncidentSupplier(i.id, s.id))} className="text-xs text-red-600 hover:underline">{t('wr.unlink', 'Unlink')}</button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {canWrite && (
          <div className="mt-2 flex gap-2">
            <select value={addSupplier} onChange={(e) => setAddSupplier(e.target.value)} className={`${input} flex-1`} aria-label={t('wr.addSupplier', 'Add a supplier')}>
              <option value="">{t('wr.pickSupplier', 'Add a supplier...')}</option>
              {suppliers.filter((s) => !linked.has(s.id)).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
            <button type="button" disabled={!addSupplier} onClick={() => act(() => api.addIncidentSupplier(i.id, addSupplier)).then(() => setAddSupplier(''))} className={`${button} border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200`}>{t('wr.link', 'Link')}</button>
          </div>
        )}
      </div>

      <div className={card}>
        <h3 className="text-sm font-semibold text-gray-900 dark:text-white">{t('wr.tasks', 'Tasks')}</h3>
        <ul className="mt-2 space-y-1">
          {data.tasks.length === 0 && <li className="text-sm text-gray-500">{t('wr.noTasks', 'No tasks yet.')}</li>}
          {data.tasks.map((task) => (
            <li key={task.id} className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={task.status === 'done'} disabled={!canWrite}
                onChange={(e) => act(() => api.setIncidentTask(i.id, task.id, e.target.checked ? 'done' : 'open'))} aria-label={task.title} />
              <span className={task.status === 'done' ? 'line-through text-gray-500' : 'text-gray-900 dark:text-white'}>{task.title}</span>
              <span className="text-xs text-gray-500">{[task.assignee_email, task.due_date && t('wr.due', 'due {{d}}', { d: task.due_date })].filter(Boolean).join(' · ')}</span>
            </li>
          ))}
        </ul>
        {canWrite && (
          <form onSubmit={(e) => { e.preventDefault(); act(() => api.addIncidentTask(i.id, { title: task.title, assignee_email: task.assignee_email || null, due_date: task.due_date || null })).then(() => setTask({ title: '', assignee_email: '', due_date: '' })); }} className="mt-2 flex flex-wrap gap-2">
            <input required maxLength={300} value={task.title} onChange={(e) => setTask({ ...task, title: e.target.value })} placeholder={t('wr.taskPlaceholder', 'New task')} className={`${input} flex-1 min-w-[160px]`} />
            <select value={task.assignee_email} onChange={(e) => setTask({ ...task, assignee_email: e.target.value })} className={input} aria-label={t('wr.assignee', 'Assignee')}>
              <option value="">{t('wr.unassigned', 'Unassigned')}</option>
              {members.map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
            <input type="date" value={task.due_date} onChange={(e) => setTask({ ...task, due_date: e.target.value })} className={input} aria-label={t('wr.dueDate', 'Due date')} />
            <button type="submit" className={`${button} border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200`}>{t('wr.addTask', 'Add task')}</button>
          </form>
        )}
      </div>

      <div className={card}>
        <h3 className="text-sm font-semibold text-gray-900 dark:text-white">{t('wr.timeline', 'Timeline')}</h3>
        {canWrite && (
          <form onSubmit={(e) => { e.preventDefault(); act(() => api.addIncidentNote(i.id, note)).then(() => setNote('')); }} className="mt-2 flex gap-2">
            <input required maxLength={4000} value={note} onChange={(e) => setNote(e.target.value)} placeholder={t('wr.notePlaceholder', 'Add a note')} className={`${input} flex-1`} />
            <button type="submit" className={`${button} bg-blue-600 text-white hover:bg-blue-700`}>{t('wr.post', 'Post')}</button>
          </form>
        )}
        <ol className="mt-3 space-y-2">
          {[...data.timeline].reverse().map((e) => (
            <li key={e.id} className="text-sm">
              <span className="text-xs text-gray-500">{utcDate(e.created_at).toLocaleString()} · {e.actor || '-'}</span>
              <p className={e.kind === 'note' ? 'text-gray-900 dark:text-white whitespace-pre-wrap' : 'text-gray-600 dark:text-gray-400 italic'}>{e.text}</p>
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}

// War room: coordinate the response to a disruption. Incidents open from a public record
// (Regulatory watch, Intel feed) or by hand. Everyone can read; admins and analysts work them.
export default function WarRoomPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const canWrite = !!user?.roles?.some((r) => r === 'admin' || r === 'analyst');
  const [params, setParams] = useSearchParams();
  const selected = params.get('incident');
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [members, setMembers] = useState<string[]>([]);
  const [status, setStatus] = useState<IncidentStatus | ''>('');
  const [showOpen, setShowOpen] = useState(false);

  const load = useCallback(() => api.listIncidents(status).then((r) => { setIncidents(r.incidents); setMembers(r.members); })
    .catch(() => setIncidents([])), [status]);
  useEffect(() => {
    load();
    const timer = window.setInterval(load, POLL_MS);
    return () => window.clearInterval(timer);
  }, [load]);
  const select = (id: string) => setParams({ incident: id });

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{t('wr.title', 'War room')}</h1>
          <p className="text-sm text-gray-500">{t('wr.subtitle', 'Coordinate the response to a disruption: owner, affected suppliers, tasks and a shared timeline.')}</p>
        </div>
        {canWrite && <button type="button" onClick={() => setShowOpen((v) => !v)} className={`${button} bg-blue-600 text-white hover:bg-blue-700`}>{t('wr.new', 'Open an incident')}</button>}
      </div>
      {showOpen && canWrite && <OpenForm onOpened={(d) => { setShowOpen(false); load(); select(d.incident.id); }} />}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        <div className="lg:col-span-2">
          <select value={status} onChange={(e) => setStatus(e.target.value as IncidentStatus | '')} className={`${input} mb-2`} aria-label={t('wr.status', 'Status')}>
            <option value="">{t('wr.all', 'All incidents')}</option>
            {(Object.keys(STATUS_LABEL) as IncidentStatus[]).map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}
          </select>
          <ul className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 divide-y divide-gray-100 dark:divide-gray-700">
            {incidents.length === 0 && <li className="p-4 text-sm text-gray-500">{t('wr.none', 'No incidents.')}</li>}
            {incidents.map((i) => (
              <li key={i.id} onClick={() => select(i.id)} className={`p-3 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700/40 ${selected === i.id ? 'bg-blue-50 dark:bg-blue-900/20' : ''}`}>
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-medium text-gray-900 dark:text-white">{i.title}</span>
                  <span className={`text-xs px-2 py-0.5 rounded-full ${STATUS_STYLE[i.status]}`}>{STATUS_LABEL[i.status]}</span>
                </div>
                <p className="text-xs text-gray-500 mt-1">
                  {i.severity} · {t('wr.counts', '{{s}} suppliers · {{t}} open tasks', { s: i.supplier_count ?? 0, t: i.open_tasks ?? 0 })}
                  {i.owner_email ? ` · ${i.owner_email}` : ''}
                </p>
              </li>
            ))}
          </ul>
        </div>
        <div className="lg:col-span-3">
          {selected ? <Detail key={selected} id={selected} members={members} canWrite={canWrite} onChanged={load} />
            : <p className="text-sm text-gray-500">{t('wr.pick', 'Pick an incident.')}</p>}
        </div>
      </div>
    </div>
  );
}
