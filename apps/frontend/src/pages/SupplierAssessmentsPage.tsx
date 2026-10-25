import { FormEvent, useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '../contexts/AuthContext';
import {
  api, AssessmentQuestion, AssessmentSent, AssessmentStatus, AssessmentTemplate, QuestionType, SubtierLink,
  SupplierAssessment,
} from '../services/api';
import { utcDate } from '../services/time';
import SignaturePanel from '../components/SignaturePanel';

const input = 'px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm bg-white dark:bg-gray-800 dark:text-white';
const button = 'px-3 py-1.5 rounded-lg text-sm font-medium disabled:opacity-50';

const STATUS_STYLE: Record<AssessmentStatus, string> = {
  sent: 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-200',
  submitted: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200',
  reviewed: 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-200',
  cancelled: 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300',
};
const STATUS_LABEL: Record<AssessmentStatus, string> = {
  sent: 'Waiting for answers', submitted: 'Answered: to review', reviewed: 'Reviewed', cancelled: 'Cancelled',
};

/** A supplier's answer as plain text (sub-tier lists are shown as a table instead). */
export function formatAnswer(q: AssessmentQuestion, value: unknown): string {
  if (value === undefined || value === null || value === '') return '-';
  if (q.type === 'yes_no') return value === 'yes' ? 'Yes' : value === 'no' ? 'No' : String(value);
  if (Array.isArray(value)) return `${value.length} listed`;
  return String(value);
}

function errorText(err: any, fallback: string): string {
  const detail = err?.response?.data?.detail;
  return typeof detail === 'string' ? detail : fallback;
}

function SentLink({ sent, onClose }: { sent: AssessmentSent; onClose: () => void }) {
  const { t } = useTranslation();
  return (
    <div className="mb-4 rounded-lg border border-blue-200 bg-blue-50 dark:bg-blue-900/20 dark:border-blue-800 p-4 text-sm">
      <p className="font-medium text-gray-900 dark:text-white">
        {sent.emailed ? t('sa.emailed', 'Emailed to {{to}}.', { to: sent.assessment.recipient_email }) : sent.note}
      </p>
      <p className="mt-2 text-gray-700 dark:text-gray-300">{t('sa.linkOnce', 'The supplier\'s personal link (shown once; it stops working when they submit):')}</p>
      <code className="block mt-1 break-all font-mono bg-white dark:bg-gray-800 rounded px-2 py-1 select-all">{sent.portal_url}</code>
      <button type="button" onClick={onClose} className="mt-2 text-blue-700 dark:text-blue-300 hover:underline">{t('common.dismiss', 'Dismiss')}</button>
    </div>
  );
}

function SendForm({ templates, onSent }: { templates: AssessmentTemplate[]; onSent: (s: AssessmentSent) => void }) {
  const { t } = useTranslation();
  const [suppliers, setSuppliers] = useState<Array<{ id: string; name: string }>>([]);
  const [form, setForm] = useState({ supplier_id: '', template_id: 'builtin:continuity', recipient_email: '',
    recipient_name: '', due_date: '', link_days: 30, send_email: true, request_reason: '' });
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.getSuppliers({ limit: 1000 }).then((r: any) => setSuppliers((r?.suppliers || r || [])
      .map((s: any) => ({ id: s.id, name: s.name })).sort((a: any, b: any) => a.name.localeCompare(b.name))))
      .catch(() => setSuppliers([]));
  }, []);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true); setError('');
    try {
      onSent(await api.sendAssessment({ ...form, due_date: form.due_date || null }));
      setForm((f) => ({ ...f, recipient_email: '', recipient_name: '', request_reason: '' }));
    } catch (err) {
      setError(errorText(err, t('sa.sendFailed', 'The questionnaire could not be sent.')));
    } finally {
      setBusy(false);
    }
  };
  const set = (key: string, value: unknown) => setForm((f) => ({ ...f, [key]: value }));
  const dueDiligence = !!templates.find((tp) => tp.id === form.template_id)?.due_diligence;
  return (
    <form onSubmit={submit} className="mb-6 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-4 grid grid-cols-1 md:grid-cols-3 gap-3">
      <select required value={form.supplier_id} onChange={(e) => set('supplier_id', e.target.value)} className={input} aria-label={t('sa.supplier', 'Supplier')}>
        <option value="">{t('sa.pickSupplier', 'Supplier...')}</option>
        {suppliers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
      </select>
      <select value={form.template_id} onChange={(e) => set('template_id', e.target.value)} className={input} aria-label={t('sa.questionnaire', 'Questionnaire')}>
        {templates.map((tp) => <option key={tp.id} value={tp.id}>{tp.name}{tp.built_in ? ` (${t('sa.builtIn', 'built-in template')})` : ''}</option>)}
      </select>
      <input type="date" value={form.due_date} onChange={(e) => set('due_date', e.target.value)} className={input} aria-label={t('sa.due', 'Answer by')} />
      <input required type="email" placeholder={t('sa.contactEmail', 'Supplier contact email')} value={form.recipient_email}
        onChange={(e) => set('recipient_email', e.target.value)} className={input} />
      <input placeholder={t('sa.contactName', 'Contact name (optional)')} value={form.recipient_name} maxLength={200}
        onChange={(e) => set('recipient_name', e.target.value)} className={input} />
      <div className="flex items-center gap-3 text-sm text-gray-700 dark:text-gray-300">
        <label className="flex items-center gap-1">{t('sa.linkDays', 'Link valid')}
          <select value={form.link_days} onChange={(e) => set('link_days', Number(e.target.value))} className={input}>
            {[7, 14, 30, 60, 90].map((d) => <option key={d} value={d}>{t('sa.days', '{{n}} days', { n: d })}</option>)}
          </select>
        </label>
        <label className="flex items-center gap-1"><input type="checkbox" checked={form.send_email} onChange={(e) => set('send_email', e.target.checked)} />{t('sa.email', 'Email it')}</label>
      </div>
      {dueDiligence && (
        <div className="md:col-span-3">
          <textarea required rows={2} maxLength={1000} value={form.request_reason} onChange={(e) => set('request_reason', e.target.value)}
            placeholder={t('sa.reasonPlaceholder', 'Why is this information needed, and why can it not reasonably be obtained another way? (required)')}
            className={`${input} w-full`} aria-label={t('sa.reason', 'Reason for asking')} />
          <p className="text-xs text-gray-500">{t('sa.reasonHint', 'Due diligence information is asked from a supplier only where necessary (CSDDD Article 8(2a)). The reason is kept with the questionnaire; the supplier does not see it.')}</p>
        </div>
      )}
      {error && <p className="md:col-span-3 text-sm text-red-600">{error}</p>}
      <div className="md:col-span-3">
        <button type="submit" disabled={busy} className={`${button} bg-blue-600 text-white hover:bg-blue-700`}>{t('sa.send', 'Send questionnaire')}</button>
      </div>
    </form>
  );
}

function Detail({ id, canWrite, onChanged, onLink }: { id: string; canWrite: boolean; onChanged: () => void; onLink: (s: AssessmentSent) => void }) {
  const { t } = useTranslation();
  const [data, setData] = useState<{ assessment: SupplierAssessment; subtier: SubtierLink[] } | null>(null);
  const [note, setNote] = useState('');
  const [error, setError] = useState('');

  const load = useCallback(() => api.getAssessment(id).then(setData)
    .catch((err) => setError(errorText(err, t('sa.loadFailed', 'Could not load the assessment.')))), [id, t]);
  useEffect(() => { load(); }, [load]);

  const act = async (fn: () => Promise<unknown>) => {
    setError('');
    try { await fn(); await load(); onChanged(); } catch (err) { setError(errorText(err, t('sa.actionFailed', 'That did not work.'))); }
  };
  if (!data) return error ? <p className="text-sm text-red-600">{error}</p> : null;
  const a = data.assessment;
  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-5">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">{a.supplier_name}: {a.template_name}</h2>
          <p className="text-xs text-gray-500">{t('sa.sentTo', 'Sent to {{to}} by {{by}}, {{at}}', { to: a.recipient_email, by: a.sent_by || '-', at: utcDate(a.sent_at).toLocaleString() })}</p>
          {a.request_reason && <p className="text-xs text-gray-500">{t('sa.askedBecause', 'Asked because: {{r}}', { r: a.request_reason })}</p>}
        </div>
        <span className={`text-xs px-2 py-1 rounded-full ${STATUS_STYLE[a.status]}`}>{STATUS_LABEL[a.status]}</span>
      </div>
      {a.submitted_at && (
        <div className="mt-4 text-sm">
          <p className="text-gray-700 dark:text-gray-300">
            {t('sa.answeredBy', 'Answered by {{name}} ({{email}}), {{at}}.', { name: a.submitted_by_name, email: a.submitted_by_email, at: utcDate(a.submitted_at).toLocaleString() })}
          </p>
          <p className="mt-1 text-xs text-amber-700 dark:text-amber-300">
            {t('sa.supplierProvided', 'Supplier-provided: these are the supplier\'s own statements, not verified findings.')}
          </p>
          {a.score !== null && (
            <p className="mt-2 font-medium text-gray-900 dark:text-white">{t('sa.score', 'Score {{score}}/100', { score: a.score })}
              <span className="ml-2 text-xs font-normal text-gray-500">{t('sa.scoreHow', 'weighted share of scored yes/no questions answered the preferred way')}</span></p>
          )}
          {a.flags.length > 0 && (
            <ul className="mt-2 space-y-1">
              {a.flags.map((f) => <li key={f.id} className="text-red-700 dark:text-red-300">⚑ {f.text} <span className="text-gray-500">({f.answer})</span></li>)}
            </ul>
          )}
        </div>
      )}
      {a.questions && a.answers && Object.keys(a.answers).length > 0 && (
        <dl className="mt-4 divide-y divide-gray-100 dark:divide-gray-700 text-sm">
          {a.questions.filter((q) => q.type !== 'subtier').map((q) => (
            <div key={q.id} className="py-2 grid grid-cols-1 md:grid-cols-3 gap-2">
              <dt className="text-gray-600 dark:text-gray-400 md:col-span-2">{q.text}</dt>
              <dd className="text-gray-900 dark:text-white whitespace-pre-wrap">{formatAnswer(q, a.answers?.[q.id])}</dd>
            </div>
          ))}
        </dl>
      )}
      {data.subtier.length > 0 && (
        <div className="mt-4">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-white">{t('sa.subtier', 'Their critical suppliers (supplier-reported)')}</h3>
          <table className="mt-2 w-full text-sm">
            <thead><tr className="text-left text-xs text-gray-500"><th>{t('sa.company', 'Company')}</th><th>{t('sa.country', 'Country')}</th><th>{t('sa.city', 'City')}</th><th>{t('sa.supplies', 'Supplies')}</th></tr></thead>
            <tbody>{data.subtier.map((l) => (
              <tr key={l.id} className="border-t border-gray-100 dark:border-gray-700 text-gray-800 dark:text-gray-200">
                <td className="py-1">{l.name}</td><td>{l.country_code || '-'}</td><td>{l.city || '-'}</td><td>{l.supplies || '-'}</td>
              </tr>))}</tbody>
          </table>
        </div>
      )}
      {(a.status === 'submitted' || a.status === 'reviewed') && <SignaturePanel key={a.id} recordType="assessment" recordId={a.id} meanings={['reviewed', 'approved']} />}
      {a.review_note && <p className="mt-4 text-sm text-gray-700 dark:text-gray-300">{t('sa.reviewNote', 'Review note ({{by}}): {{note}}', { by: a.reviewed_by, note: a.review_note })}</p>}
      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
      {canWrite && a.status === 'submitted' && (
        <div className="mt-4 flex flex-wrap gap-2 items-center">
          <input value={note} onChange={(e) => setNote(e.target.value)} maxLength={2000} placeholder={t('sa.notePlaceholder', 'Review note (optional)')} className={`${input} flex-1 min-w-[200px]`} />
          <button type="button" onClick={() => act(() => api.reviewAssessment(a.id, note))} className={`${button} bg-green-600 text-white hover:bg-green-700`}>{t('sa.markReviewed', 'Mark reviewed')}</button>
        </div>
      )}
      {canWrite && a.status === 'sent' && (
        <div className="mt-4 flex gap-2">
          <button type="button" onClick={() => act(async () => onLink(await api.resendAssessment(a.id)))} className={`${button} border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200`}>{t('sa.resend', 'New link')}</button>
          <button type="button" onClick={() => act(() => api.cancelAssessment(a.id))} className={`${button} text-red-600 hover:underline`}>{t('sa.cancel', 'Cancel')}</button>
        </div>
      )}
    </div>
  );
}

const QUESTION_TYPES: Array<{ value: QuestionType; label: string }> = [
  { value: 'yes_no', label: 'Yes / no' }, { value: 'text', label: 'Text' }, { value: 'number', label: 'Number' },
  { value: 'date', label: 'Date' }, { value: 'choice', label: 'One of several options' }, { value: 'subtier', label: 'List of their suppliers' },
];
interface DraftQuestion { text: string; type: QuestionType; required: boolean; good: '' | 'yes' | 'no'; weight: number; options: string }
const blankQuestion = (): DraftQuestion => ({ text: '', type: 'yes_no', required: true, good: 'yes', weight: 3, options: '' });

function TemplateEditor({ onCreated }: { onCreated: () => void }) {
  const { t } = useTranslation();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [questions, setQuestions] = useState<DraftQuestion[]>([blankQuestion()]);
  const [error, setError] = useState('');
  const set = (i: number, patch: Partial<DraftQuestion>) => setQuestions((qs) => qs.map((q, n) => (n === i ? { ...q, ...patch } : q)));
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    try {
      await api.createAssessmentTemplate({ name, description, questions: questions.map((q, i) => ({
        id: `q${i + 1}`, text: q.text, type: q.type, required: q.required,
        ...(q.type === 'yes_no' && q.good ? { good: q.good, weight: q.weight } : {}),
        ...(q.type === 'choice' ? { options: q.options.split(',').map((o) => o.trim()).filter(Boolean) } : {}),
      })) });
      setName(''); setDescription(''); setQuestions([blankQuestion()]);
      onCreated();
    } catch (err) {
      setError(errorText(err, t('sa.templateFailed', 'The questionnaire could not be saved.')));
    }
  };
  return (
    <form onSubmit={submit} className="mt-3 space-y-3">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <input required maxLength={100} value={name} onChange={(e) => setName(e.target.value)} placeholder={t('sa.templateName', 'Questionnaire name')} className={input} />
        <input maxLength={500} value={description} onChange={(e) => setDescription(e.target.value)} placeholder={t('sa.templateDescription', 'Description (optional)')} className={input} />
      </div>
      {questions.map((q, i) => (
        <div key={i} className="grid grid-cols-1 md:grid-cols-[3fr_1.3fr_auto_auto_auto] gap-2 items-center">
          <input required maxLength={500} value={q.text} onChange={(e) => set(i, { text: e.target.value })} placeholder={t('sa.questionText', 'Question {{n}}', { n: i + 1 })} className={input} />
          <select value={q.type} onChange={(e) => set(i, { type: e.target.value as QuestionType })} className={input}>
            {QUESTION_TYPES.map((qt) => <option key={qt.value} value={qt.value}>{qt.label}</option>)}
          </select>
          <label className="text-xs text-gray-600 dark:text-gray-400 flex items-center gap-1"><input type="checkbox" checked={q.required} onChange={(e) => set(i, { required: e.target.checked })} />{t('sa.required', 'Required')}</label>
          {q.type === 'yes_no' ? (
            <select value={q.good} onChange={(e) => set(i, { good: e.target.value as DraftQuestion['good'] })} className={input} aria-label={t('sa.preferred', 'Preferred answer')}>
              <option value="">{t('sa.notScored', 'Not scored')}</option><option value="yes">{t('sa.goodYes', 'Yes is good')}</option><option value="no">{t('sa.goodNo', 'No is good')}</option>
            </select>
          ) : q.type === 'choice' ? (
            <input value={q.options} onChange={(e) => set(i, { options: e.target.value })} placeholder={t('sa.options', 'Options, comma-separated')} className={input} />
          ) : <span />}
          <button type="button" onClick={() => setQuestions((qs) => qs.filter((_, n) => n !== i))} disabled={questions.length === 1} className="text-xs text-red-600 hover:underline disabled:opacity-40">{t('sa.removeQuestion', 'Remove')}</button>
        </div>
      ))}
      {error && <p className="text-sm text-red-600">{error}</p>}
      <div className="flex gap-3">
        <button type="button" onClick={() => setQuestions((qs) => [...qs, blankQuestion()])} className="text-sm text-blue-600 hover:underline">{t('sa.addQuestion', '+ Add a question')}</button>
        <button type="submit" className={`${button} bg-blue-600 text-white hover:bg-blue-700`}>{t('sa.saveTemplate', 'Save questionnaire')}</button>
      </div>
    </form>
  );
}

// Supplier assessments: send questionnaires to supplier contacts, read their answers
// (supplier-provided), and review them. Read-only roles can view.
export default function SupplierAssessmentsPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const canWrite = !!user?.roles?.some((r) => r === 'admin' || r === 'analyst');
  const [templates, setTemplates] = useState<AssessmentTemplate[]>([]);
  const [rows, setRows] = useState<SupplierAssessment[]>([]);
  const [status, setStatus] = useState<AssessmentStatus | ''>('');
  const [selected, setSelected] = useState<string | null>(null);
  const [sent, setSent] = useState<AssessmentSent | null>(null);
  const [showSend, setShowSend] = useState(false);
  const [showTemplates, setShowTemplates] = useState(false);
  const [error, setError] = useState('');

  const loadTemplates = useCallback(() => api.listAssessmentTemplates().then(setTemplates).catch(() => setTemplates([])), []);
  const load = useCallback(() => api.listAssessments({ status }).then(setRows)
    .catch((err) => setError(errorText(err, t('sa.listFailed', 'Could not load the assessments.')))), [status, t]);
  useEffect(() => { loadTemplates(); }, [loadTemplates]);
  useEffect(() => { load(); }, [load]);

  const onSent = (s: AssessmentSent) => { setSent(s); setShowSend(false); setSelected(s.assessment.id); load(); };
  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{t('sa.title', 'Supplier assessments')}</h1>
          <p className="text-sm text-gray-500">{t('sa.subtitle', 'Questionnaires your suppliers answer through a personal link, without an account.')}</p>
        </div>
        <div className="flex gap-2">
          <button type="button" onClick={() => setShowTemplates((v) => !v)} className={`${button} border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200`}>{t('sa.questionnaires', 'Questionnaires')}</button>
          {canWrite && <button type="button" onClick={() => setShowSend((v) => !v)} className={`${button} bg-blue-600 text-white hover:bg-blue-700`}>{t('sa.new', 'Send a questionnaire')}</button>}
        </div>
      </div>
      {sent && <SentLink sent={sent} onClose={() => setSent(null)} />}
      {showSend && canWrite && <SendForm templates={templates} onSent={onSent} />}
      {showTemplates && (
        <div className="mb-6 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-4">
          <ul className="divide-y divide-gray-100 dark:divide-gray-700">
            {templates.map((tp) => (
              <li key={tp.id} className="py-2 flex items-start justify-between gap-3 text-sm">
                <div>
                  <p className="font-medium text-gray-900 dark:text-white">{tp.name} <span className="text-xs text-gray-500">· {t('sa.nQuestions', '{{n}} questions', { n: tp.questions.length })}{tp.built_in ? ` · ${t('sa.builtIn', 'built-in template')}` : ''}</span></p>
                  {tp.description && <p className="text-xs text-gray-500">{tp.description}</p>}
                </div>
                {canWrite && !tp.built_in && <button type="button" onClick={() => api.archiveAssessmentTemplate(tp.id).then(loadTemplates)} className="text-xs text-red-600 hover:underline">{t('sa.retire', 'Retire')}</button>}
              </li>
            ))}
          </ul>
          {canWrite && <TemplateEditor onCreated={loadTemplates} />}
        </div>
      )}
      <div className="flex items-center gap-2 mb-3">
        <select value={status} onChange={(e) => setStatus(e.target.value as AssessmentStatus | '')} className={input} aria-label={t('sa.status', 'Status')}>
          <option value="">{t('sa.all', 'All')}</option>
          {(Object.keys(STATUS_LABEL) as AssessmentStatus[]).map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}
        </select>
      </div>
      {error && <p className="text-sm text-red-600 mb-3">{error}</p>}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 overflow-hidden">
          {rows.length === 0 ? (
            <p className="p-6 text-sm text-gray-500">{t('sa.none', 'No assessments yet.')}</p>
          ) : (
            <table className="w-full text-sm">
              <thead className="bg-gray-50 dark:bg-gray-900/40 text-left text-xs text-gray-500">
                <tr><th className="px-3 py-2">{t('sa.supplier', 'Supplier')}</th><th>{t('sa.questionnaire', 'Questionnaire')}</th><th>{t('sa.statusCol', 'Status')}</th><th>{t('sa.scoreCol', 'Score')}</th></tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} onClick={() => setSelected(r.id)} className={`cursor-pointer border-t border-gray-100 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700/40 ${selected === r.id ? 'bg-blue-50 dark:bg-blue-900/20' : ''}`}>
                    <td className="px-3 py-2 text-gray-900 dark:text-white">{r.supplier_name}<div className="text-xs text-gray-500">{r.due_date ? t('sa.dueOn', 'due {{d}}', { d: r.due_date }) : ''}</div></td>
                    <td className="text-gray-700 dark:text-gray-300">{r.template_name}</td>
                    <td><span className={`text-xs px-2 py-0.5 rounded-full ${STATUS_STYLE[r.status]}`}>{STATUS_LABEL[r.status]}</span></td>
                    <td className="text-gray-900 dark:text-white">{r.score ?? '-'}{r.flags.length ? <span className="ml-1 text-xs text-red-600">⚑{r.flags.length}</span> : null}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
        <div>{selected && <Detail key={selected} id={selected} canWrite={canWrite} onChanged={load} onLink={setSent} />}</div>
      </div>
    </div>
  );
}
