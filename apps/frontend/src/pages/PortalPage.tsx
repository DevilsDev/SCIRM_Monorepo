import { FormEvent, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { AssessmentQuestion } from '../services/api';
import { portal, PortalAssessment, portalToken } from '../services/portal';

type Answers = Record<string, unknown>;
interface LinkRow { name: string; country: string; city: string; supplies: string }

const field = 'w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm outline-none focus:ring-2 focus:ring-blue-500 text-gray-900 dark:text-white bg-white dark:bg-gray-800';

function errorText(err: any, fallback: string): string {
  const detail = err?.response?.data?.detail;
  return typeof detail === 'string' ? detail : fallback;
}

/** Sub-tier rows as the form edits them (the API takes and returns country codes). */
function linkRows(value: unknown): LinkRow[] {
  const rows = Array.isArray(value) ? value : [];
  const mapped = rows.map((r: any) => ({ name: r?.name ?? '', country: r?.country ?? r?.country_code ?? '',
    city: r?.city ?? '', supplies: r?.supplies ?? '' }));
  return mapped.length ? mapped : [{ name: '', country: '', city: '', supplies: '' }];
}

function QuestionField({ q, value, onChange }: { q: AssessmentQuestion; value: unknown; onChange: (v: unknown) => void }) {
  const { t } = useTranslation();
  if (q.type === 'yes_no') {
    return (
      <div className="flex gap-4">
        {(['yes', 'no'] as const).map((option) => (
          <label key={option} className="flex items-center gap-2 text-sm text-gray-800 dark:text-gray-200">
            <input type="radio" name={q.id} checked={value === option} onChange={() => onChange(option)} />
            {option === 'yes' ? t('portal.yes', 'Yes') : t('portal.no', 'No')}
          </label>
        ))}
      </div>
    );
  }
  if (q.type === 'choice') {
    return (
      <select value={(value as string) ?? ''} onChange={(e) => onChange(e.target.value)} className={field}>
        <option value="">{t('portal.choose', 'Choose...')}</option>
        {(q.options || []).map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
    );
  }
  if (q.type === 'subtier') {
    const rows = linkRows(value);
    const set = (i: number, key: keyof LinkRow, v: string) =>
      onChange(rows.map((r, n) => (n === i ? { ...r, [key]: v } : r)));
    return (
      <div className="space-y-2">
        {rows.map((r, i) => (
          <div key={i} className="grid grid-cols-1 sm:grid-cols-[2fr_80px_1fr_2fr_auto] gap-2">
            <input value={r.name} onChange={(e) => set(i, 'name', e.target.value)} maxLength={200}
              placeholder={t('portal.company', 'Company')} className={field} aria-label={t('portal.company', 'Company')} />
            <input value={r.country} onChange={(e) => set(i, 'country', e.target.value.toUpperCase())} maxLength={2}
              placeholder={t('portal.country', 'DE')} className={field} aria-label={t('portal.countryCode', 'Country code')} />
            <input value={r.city} onChange={(e) => set(i, 'city', e.target.value)} maxLength={100}
              placeholder={t('portal.city', 'City')} className={field} aria-label={t('portal.city', 'City')} />
            <input value={r.supplies} onChange={(e) => set(i, 'supplies', e.target.value)} maxLength={200}
              placeholder={t('portal.supplies', 'What they supply')} className={field} aria-label={t('portal.supplies', 'What they supply')} />
            <button type="button" onClick={() => onChange(rows.filter((_, n) => n !== i))}
              className="text-xs text-red-600 hover:underline px-2">{t('portal.remove', 'Remove')}</button>
          </div>
        ))}
        {rows.length < 50 && (
          <button type="button" onClick={() => onChange([...rows, { name: '', country: '', city: '', supplies: '' }])}
            className="text-sm text-blue-600 hover:underline">{t('portal.addCompany', '+ Add a company')}</button>
        )}
      </div>
    );
  }
  if (q.type === 'text') {
    return <textarea rows={3} maxLength={4000} value={(value as string) ?? ''} onChange={(e) => onChange(e.target.value)} className={field} />;
  }
  return (
    <input type={q.type === 'number' ? 'number' : 'date'} value={(value as string | number) ?? ''}
      onChange={(e) => onChange(e.target.value)} className={`${field} max-w-xs`} />
  );
}

// /portal#<token>: a supplier answers a questionnaire. No account; the link is the key.
// The token stays in the address until the answers are submitted, so the same link can be
// opened again to finish a saved draft.
export default function PortalPage() {
  const { t } = useTranslation();
  const [token] = useState(() => portalToken(window.location.hash));
  const [assessment, setAssessment] = useState<PortalAssessment | null>(null);
  const [answers, setAnswers] = useState<Answers>({});
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [done, setDone] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!token) return;
    portal.load(token)
      .then((a) => { setAssessment(a); setAnswers(a.answers || {}); setName(a.recipient_name || ''); })
      .catch((err) => setError(errorText(err, t('portal.loadFailed', 'The questionnaire could not be opened.'))));
  }, [token, t]);

  const save = async () => {
    setBusy(true); setError(''); setNotice('');
    try {
      await portal.save(token, answers);
      setNotice(t('portal.saved', 'Draft saved. Open the same link to continue.'));
    } catch (err) {
      setError(errorText(err, t('portal.saveFailed', 'The draft could not be saved.')));
    } finally {
      setBusy(false);
    }
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true); setError(''); setNotice('');
    try {
      setDone(await portal.submit(token, answers, name, email));
      window.history.replaceState(null, '', window.location.pathname);  // the link is spent
    } catch (err) {
      setError(errorText(err, t('portal.submitFailed', 'The answers could not be sent.')));
    } finally {
      setBusy(false);
    }
  };

  const card = 'w-full max-w-3xl bg-white dark:bg-gray-800 rounded-xl shadow-lg p-8';
  if (done || !token || (error && !assessment)) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-100 dark:bg-gray-900 p-4">
        <div className={`${card} text-center`}>
          <h1 className="text-xl font-bold text-gray-900 dark:text-white mb-3">{t('portal.title', 'Supplier questionnaire')}</h1>
          <p className={`text-sm ${done ? 'text-gray-700 dark:text-gray-300' : 'text-red-600'}`}>
            {done || error || t('portal.noToken', 'This page needs the personal link you received by email.')}
          </p>
        </div>
      </div>
    );
  }
  if (!assessment) {
    return <div className="min-h-screen flex items-center justify-center bg-gray-100 dark:bg-gray-900 text-sm text-gray-500">{t('common.loading', 'Loading...')}</div>;
  }
  return (
    <div className="min-h-screen bg-gray-100 dark:bg-gray-900 py-10 px-4 flex justify-center">
      <form onSubmit={submit} className={card}>
        <p className="text-xs uppercase tracking-wide text-gray-500">{t('portal.requestedBy', 'Requested by {{org}}', { org: assessment.organization_name || '' })}</p>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white mt-1">{assessment.template_name}</h1>
        <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
          {t('portal.for', 'For {{supplier}}', { supplier: assessment.supplier_name || '' })}
          {assessment.due_date ? ` · ${t('portal.due', 'please answer by {{date}}', { date: assessment.due_date })}` : ''}
        </p>
        <p className="text-sm text-gray-600 dark:text-gray-400 mt-3">
          {t('portal.intro', 'Your answers go only to the organization that sent this link. You can save a draft and come back with the same link until you submit. Questions marked * are required.')}
        </p>
        <ol className="mt-6 space-y-6">
          {assessment.questions.map((q, i) => (
            <li key={q.id}>
              <p className="text-sm font-medium text-gray-900 dark:text-white mb-2">
                {i + 1}. {q.text}{q.required ? ' *' : ''}
              </p>
              {q.help && <p className="text-xs text-gray-500 mb-2">{q.help}</p>}
              <QuestionField q={q} value={answers[q.id]} onChange={(v) => setAnswers((a) => ({ ...a, [q.id]: v }))} />
            </li>
          ))}
        </ol>
        <div className="mt-8 border-t border-gray-200 dark:border-gray-700 pt-6 grid grid-cols-1 sm:grid-cols-2 gap-3">
          <label className="text-sm text-gray-700 dark:text-gray-300">{t('portal.yourName', 'Your name')}
            <input required maxLength={200} value={name} onChange={(e) => setName(e.target.value)} className={`${field} mt-1`} />
          </label>
          <label className="text-sm text-gray-700 dark:text-gray-300">{t('portal.yourEmail', 'Your work email')}
            <input required type="email" maxLength={254} value={email} onChange={(e) => setEmail(e.target.value)} className={`${field} mt-1`} />
          </label>
        </div>
        {error && <p className="mt-4 text-sm text-red-600">{error}</p>}
        {notice && <p className="mt-4 text-sm text-green-700 dark:text-green-400">{notice}</p>}
        <div className="mt-6 flex flex-wrap gap-3">
          <button type="submit" disabled={busy} className="px-5 py-2.5 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50">
            {t('portal.submit', 'Submit answers')}
          </button>
          <button type="button" onClick={save} disabled={busy} className="px-5 py-2.5 border border-gray-300 dark:border-gray-600 rounded-lg text-sm text-gray-700 dark:text-gray-200 disabled:opacity-50">
            {t('portal.saveDraft', 'Save draft')}
          </button>
        </div>
        <p className="mt-3 text-xs text-gray-500">{t('portal.final', 'After you submit, the answers cannot be changed and this link stops working.')}</p>
      </form>
    </div>
  );
}
