import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '../contexts/AuthContext';
import { ActionMode, ActionPolicyEntry, ActionProposal, AiRun, api } from '../services/api';
import { utcDate } from '../services/time';

const input = 'px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm bg-white dark:bg-gray-800 dark:text-white';
const button = 'px-3 py-1.5 rounded-lg text-sm font-medium disabled:opacity-50';
const card = 'rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800';

const MODE_LABEL: Record<ActionMode, string> = {
  never: 'Never', approval: 'Propose for approval', allowed: 'Do it directly',
};
const STATUS_STYLE: Record<ActionProposal['status'], string> = {
  pending: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200',
  executed: 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-200',
  rejected: 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-200',
  failed: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-200',
};

/** One line for a run: who, what, the outcome and the model (or why there was none). */
export function describeRun(run: AiRun): string {
  const what = run.kind === 'ask'
    ? `Ask about ${(run.input.supplier as string) || 'a supplier'}: "${run.input.question ?? ''}"`
    : `Tool ${String(run.input.tool ?? '')}`;
  const model = run.llm?.model ? ` · ${run.llm.model}` : run.method === 'extractive' ? ' · no model (records\' own wording)' : '';
  return `${what} → ${run.status}${run.degraded ? ' (degraded)' : ''}${model}`;
}

function errorText(err: any, fallback: string): string {
  const detail = err?.response?.data?.detail;
  return typeof detail === 'string' ? detail : fallback;
}

function Approvals({ canDecide }: { canDecide: boolean }) {
  const { t } = useTranslation();
  const [rows, setRows] = useState<ActionProposal[]>([]);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [link, setLink] = useState('');
  const [error, setError] = useState('');
  const load = useCallback(() => api.listProposals().then(setRows).catch(() => setRows([])), []);
  useEffect(() => { load(); const timer = window.setInterval(load, 30000); return () => window.clearInterval(timer); }, [load]);
  const decide = async (p: ActionProposal, approve: boolean) => {
    setError(''); setLink('');
    try {
      const done = await api.decideProposal(p.id, approve, notes[p.id] || '');
      if (done.portal_url) setLink(done.portal_url);
      load();
    } catch (err) { setError(errorText(err, t('ai.decideFailed', 'That did not work.'))); }
  };
  return (
    <div className={`${card} divide-y divide-gray-100 dark:divide-gray-700`}>
      {link && <p className="p-3 text-sm bg-blue-50 dark:bg-blue-900/20">{t('ai.linkOnce', "The supplier's personal link (shown once):")} <code className="break-all select-all">{link}</code></p>}
      {error && <p className="p-3 text-sm text-red-600">{error}</p>}
      {rows.length === 0 && <p className="p-4 text-sm text-gray-500">{t('ai.noProposals', 'No actions proposed by AI agents.')}</p>}
      {rows.map((p) => (
        <div key={p.id} className="p-4 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <span className={`text-xs px-2 py-0.5 rounded-full ${STATUS_STYLE[p.status]}`}>{p.status}</span>
            <span className="font-medium text-gray-900 dark:text-white">{p.label}</span>
            <span className="text-xs text-gray-500">{t('ai.proposedBy', 'proposed by {{who}} ({{via}}), {{at}}', { who: p.proposed_by, via: p.proposed_via.toUpperCase(), at: utcDate(p.created_at).toLocaleString() })}</span>
          </div>
          <p className="mt-1 text-gray-700 dark:text-gray-300">{p.summary}</p>
          <pre className="mt-1 text-xs bg-gray-50 dark:bg-gray-900/40 rounded p-2 overflow-x-auto">{JSON.stringify(p.params, null, 2)}</pre>
          {p.status === 'pending' && canDecide && (
            <div className="mt-2 flex flex-wrap gap-2">
              <input value={notes[p.id] || ''} onChange={(e) => setNotes({ ...notes, [p.id]: e.target.value })} maxLength={1000}
                placeholder={t('ai.note', 'Note (optional)')} className={`${input} flex-1 min-w-[180px]`} />
              <button type="button" onClick={() => decide(p, true)} className={`${button} bg-green-600 text-white hover:bg-green-700`}>{t('ai.approve', 'Approve and run')}</button>
              <button type="button" onClick={() => decide(p, false)} className={`${button} border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200`}>{t('ai.reject', 'Reject')}</button>
            </div>
          )}
          {p.status !== 'pending' && (
            <p className="mt-1 text-xs text-gray-500">
              {t('ai.decided', '{{status}} by {{who}}', { status: p.status, who: p.decided_by || '-' })}
              {p.decision_note ? ` · ${p.decision_note}` : ''}
              {p.result && (p.result as any).error ? ` · ${(p.result as any).error}` : ''}
            </p>
          )}
        </div>
      ))}
    </div>
  );
}

function Policy({ isAdmin }: { isAdmin: boolean }) {
  const { t } = useTranslation();
  const [entries, setEntries] = useState<ActionPolicyEntry[]>([]);
  const [error, setError] = useState('');
  useEffect(() => { api.getActionPolicy().then((r) => setEntries(r.actions)).catch(() => setEntries([])); }, []);
  const set = async (action: string, mode: ActionMode) => {
    setError('');
    try { setEntries((await api.setActionPolicy(action, mode)).actions); } catch (err) { setError(errorText(err, t('ai.policyFailed', 'The policy could not be changed.'))); }
  };
  return (
    <div className={`${card} p-4`}>
      <p className="text-sm text-gray-600 dark:text-gray-400">{t('ai.policyHint', 'What AI agents (for example an MCP client such as Claude) may do in your organization. Reading data is set by their API key; these are the changes they can make. Anything that reaches outside the organization always needs a person.')}</p>
      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
      <table className="mt-3 w-full text-sm">
        <tbody>
          {entries.map((e) => (
            <tr key={e.action} className="border-t border-gray-100 dark:border-gray-700">
              <td className="py-2 text-gray-900 dark:text-white">{e.label}<div className="text-xs text-gray-500 font-mono">{e.action}</div></td>
              <td className="text-right">
                {isAdmin ? (
                  <select value={e.mode} onChange={(ev) => set(e.action, ev.target.value as ActionMode)} className={input} aria-label={e.label}>
                    {(['never', 'approval', 'allowed'] as ActionMode[]).filter((m) => !(e.external && m === 'allowed'))
                      .map((m) => <option key={m} value={m}>{MODE_LABEL[m]}</option>)}
                  </select>
                ) : <span className="text-gray-700 dark:text-gray-300">{MODE_LABEL[e.mode]}</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Runs() {
  const { t } = useTranslation();
  const [runs, setRuns] = useState<AiRun[]>([]);
  const [open, setOpen] = useState<AiRun | null>(null);
  const [error, setError] = useState('');
  useEffect(() => { api.listAiRuns().then(setRuns).catch((err) => setError(errorText(err, t('ai.runsFailed', 'Could not load the AI runs.')))); }, [t]);
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <ul className={`${card} divide-y divide-gray-100 dark:divide-gray-700`}>
        {error && <li className="p-3 text-sm text-red-600">{error}</li>}
        {!error && runs.length === 0 && <li className="p-4 text-sm text-gray-500">{t('ai.noRuns', 'No AI runs yet.')}</li>}
        {runs.map((r) => (
          <li key={r.id} onClick={() => api.getAiRun(r.id).then(setOpen)} className={`p-3 text-sm cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700/40 ${open?.id === r.id ? 'bg-blue-50 dark:bg-blue-900/20' : ''}`}>
            <p className={r.degraded ? 'text-amber-700 dark:text-amber-300' : 'text-gray-900 dark:text-white'}>{describeRun(r)}</p>
            <p className="text-xs text-gray-500">{utcDate(r.created_at).toLocaleString()} · {r.actor} · {r.latency_ms ?? '-'} ms</p>
          </li>
        ))}
      </ul>
      {open && (
        <div className={`${card} p-4 text-sm`}>
          <p className="font-medium text-gray-900 dark:text-white">{describeRun(open)}</p>
          <p className="text-xs text-gray-500">{t('ai.method', 'Method: {{m}}', { m: open.method || '-' })}{open.llm ? ` · ${open.llm.provider || '-'} · ${t('ai.calls', '{{c}} call(s), {{f}} failure(s)', { c: open.llm.calls, f: open.llm.failures })}` : ''}</p>
          {open.output?.note && <p className="mt-2 text-gray-700 dark:text-gray-300">{open.output.note}</p>}
          {(open.output?.claims || []).length > 0 && (
            <div className="mt-2">
              <p className="text-xs font-semibold text-gray-600 dark:text-gray-400">{t('ai.kept', 'Kept by the citation checker')}</p>
              <ul className="list-disc ml-5">{open.output!.claims!.map((c, i) => <li key={i}>{c.text}</li>)}</ul>
            </div>
          )}
          {(open.output?.removed || []).length > 0 && (
            <div className="mt-2">
              <p className="text-xs font-semibold text-red-700 dark:text-red-300">{t('ai.removed', 'Removed by the citation checker')}</p>
              <ul className="list-disc ml-5">{open.output!.removed!.map((c, i) => <li key={i}>{c.text} <span className="text-xs text-gray-500">({(c.reasons || []).join('; ')})</span></li>)}</ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// AI control centre: what AI agents may do (the action policy), what they proposed (the
// approval queue) and what AI did (the run log, for administrators and auditors).
export default function AiControlPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const roles = user?.roles || [];
  const isAdmin = roles.includes('admin');
  const canDecide = roles.some((r) => r === 'admin' || r === 'analyst');
  const canReadRuns = roles.some((r) => r === 'admin' || r === 'auditor');
  const [tab, setTab] = useState<'approvals' | 'policy' | 'runs'>('approvals');
  const tabs: Array<[typeof tab, string]> = [['approvals', t('ai.tabApprovals', 'Approvals')], ['policy', t('ai.tabPolicy', 'Policy')],
    ...(canReadRuns ? [['runs', t('ai.tabRuns', 'Run log')] as [typeof tab, string]] : [])];
  return (
    <div className="p-6 max-w-7xl mx-auto">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{t('ai.title', 'AI control centre')}</h1>
      <p className="text-sm text-gray-500 mt-1">{t('ai.subtitle', 'What AI agents may do, what they proposed, and what AI did, with the evidence.')}</p>
      <div className="mt-4 mb-4 flex gap-2">
        {tabs.map(([key, label]) => (
          <button key={key} type="button" onClick={() => setTab(key)} className={`${button} ${tab === key ? 'bg-blue-600 text-white' : 'border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200'}`}>{label}</button>
        ))}
      </div>
      {tab === 'approvals' && <Approvals canDecide={canDecide} />}
      {tab === 'policy' && <Policy isAdmin={isAdmin} />}
      {tab === 'runs' && canReadRuns && <Runs />}
    </div>
  );
}
