import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api, FeedbackSummary } from '../services/api';

function pct(value: number | null): string {
  return value === null ? '–' : `${Math.round(value * 100)}%`;
}

function Metric({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-3">
      <p className="text-xs text-gray-500 dark:text-gray-400">{label}</p>
      <p className="text-2xl font-semibold text-gray-900 dark:text-white">{value}</p>
      <p className="text-[11px] text-gray-500 dark:text-gray-400">{detail}</p>
    </div>
  );
}

// What the team's ratings say about matches and answers (admins and auditors).
export default function PilotMetrics() {
  const { t } = useTranslation();
  const [data, setData] = useState<FeedbackSummary | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    api.getFeedbackSummary(90)
      .then(setData)
      .catch(() => setError(t('pilot.failed', 'Could not load the ratings.')));
  }, [t]);

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
      <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-1">{t('pilot.title', 'Pilot metrics')}</h2>
      <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">
        {t('pilot.hint', "From your team's ratings of matched records and answers over the last 90 days.")}
      </p>
      {error && <p className="text-sm text-red-600">{error}</p>}
      {data && (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <Metric
              label={t('pilot.useful', 'Matched records rated useful')}
              value={pct(data.records.useful_rate)}
              detail={t('pilot.usefulDetail', '{{useful}} of {{rated}} rated · {{wrong}} wrong supplier ({{wrongRate}})',
                { useful: data.records.useful, rated: data.records.rated, wrong: data.records.wrong_supplier,
                  wrongRate: pct(data.records.wrong_supplier_rate) })}
            />
            <Metric
              label={t('pilot.helpful', 'Answers rated helpful')}
              value={pct(data.answers.helpful_rate)}
              detail={t('pilot.helpfulDetail', '{{helpful}} of {{rated}} rated', { helpful: data.answers.helpful, rated: data.answers.rated })}
            />
            <Metric
              label={t('pilot.citations', 'Citations not reported wrong')}
              value={pct(data.citations.estimated_correct_rate)}
              detail={t('pilot.citationsDetail', '{{wrong}} reported wrong, of {{total}} in rated answers',
                { wrong: data.citations.reported_incorrect_in_rated_answers, total: data.citations.in_rated_answers })}
            />
          </div>
          <p className="text-[11px] text-gray-400 mt-3">
            {data.raters === 1
              ? t('pilot.noteOne', '1 person rated. Few ratings make these numbers unreliable; unreported citations count as correct.')
              : t('pilot.note', '{{raters}} people rated. Few ratings make these numbers unreliable; unreported citations count as correct.',
                { raters: data.raters })}
          </p>
        </>
      )}
    </div>
  );
}
