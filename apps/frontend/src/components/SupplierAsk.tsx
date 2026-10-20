import { FormEvent, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api, EvidenceAnswer } from '../services/api';
import SeverityBadge from './SeverityBadge';

const METHOD_LABELS: Record<string, string> = {
  extractive: 'Composed from the records themselves (no AI model configured)',
  llm: 'Written by the AI model from the records, then checked against them',
  extractive_after_llm_rejected: "The AI model's answer failed the citation check; showing the records' own wording",
};

// Renders "... text [S1][S2]" with the citation markers as links to the record list.
function ClaimText({ text }: { text: string }) {
  const parts = text.split(/(\[S\d+\])/g);
  return (
    <>
      {parts.map((part, i) => {
        const m = part.match(/^\[(S\d+)\]$/);
        return m ? (
          <a key={i} href={`#cite-${m[1]}`} className="text-blue-600 text-[10px] align-super ml-0.5">{m[1]}</a>
        ) : (
          <span key={i}>{part}</span>
        );
      })}
    </>
  );
}

export default function SupplierAsk({ supplierId }: { supplierId: string }) {
  const { t } = useTranslation();
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState<EvidenceAnswer | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (question.trim().length < 3) return;
    setLoading(true);
    setError('');
    try {
      setAnswer(await api.askAboutSupplier(supplierId, question.trim()));
    } catch (err: any) {
      setAnswer(null);
      setError(err?.response?.status === 503
        ? t('ask.unavailable', 'Answering is temporarily unavailable.')
        : t('ask.failed', 'Could not answer that question.'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-3">
      <form onSubmit={submit} className="flex gap-2">
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          maxLength={500}
          placeholder={t('ask.placeholder', 'e.g. Any sterility problems? Are their products held at the US border?')}
          className="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm bg-white dark:bg-gray-800 focus:ring-2 focus:ring-blue-500 outline-none"
        />
        <button
          type="submit"
          disabled={loading || question.trim().length < 3}
          className="px-3 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? t('ask.asking', 'Checking...') : t('ask.ask', 'Ask')}
        </button>
      </form>

      {error && <p className="text-sm text-red-500">{error}</p>}

      {answer && (
        <div className="space-y-3">
          <p className="text-xs text-gray-500 dark:text-gray-400">{answer.note}</p>
          {answer.status === 'insufficient_evidence' && (
            <p className="text-sm text-gray-600 dark:text-gray-300">
              {t('ask.insufficient', 'The matching records do not support an answer to this question.')}
            </p>
          )}
          {answer.claims.length > 0 && (
            <ul className="space-y-1.5 list-disc pl-5">
              {answer.claims.map((c, i) => (
                <li key={i} className="text-sm text-gray-800 dark:text-gray-200"><ClaimText text={c.text} /></li>
              ))}
            </ul>
          )}
          {answer.citations.length > 0 && (
            <ol className="space-y-1 text-xs border-t border-gray-100 dark:border-gray-700 pt-2">
              {answer.citations.map((c) => (
                <li key={c.id} id={`cite-${c.id}`} className="flex items-center gap-2 flex-wrap">
                  <span className="font-mono text-gray-400">{c.id}</span>
                  <SeverityBadge severity={c.severity} />
                  <span className="text-gray-500">{c.source_label} · {c.published_at}</span>
                  {c.url ? (
                    <a href={c.url} target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline">{c.title}</a>
                  ) : (
                    <span>{c.title}</span>
                  )}
                  {c.match_kind === 'exposure' && (
                    <span className="text-amber-600">{t('ask.exposure', '(country exposure, not an incident)')}</span>
                  )}
                </li>
              ))}
            </ol>
          )}
          <p className="text-[10px] text-gray-400">
            {METHOD_LABELS[answer.method] || ''}
            {answer.removed.length > 0 && ` · ${t('ask.removed', '{{count}} unsupported sentence(s) removed by the citation check', { count: answer.removed.length })}`}
          </p>
        </div>
      )}
    </div>
  );
}
