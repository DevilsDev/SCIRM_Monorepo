import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api, SignalMatch, SupplierSignals as SupplierSignalsData } from '../services/api';
import SeverityBadge from './SeverityBadge';

// How a record was linked to the supplier, in words a buyer can check.
function matchReason(m: SignalMatch, t: (key: string, fallback: string, opts?: any) => string) {
  switch (m.match_type) {
    case 'name_exact':
      return t('signals.matchExact', 'Names "{{name}}"', { name: m.matched_on });
    case 'name_contains':
    case 'name_similar':
      return t('signals.matchSimilar', 'Names "{{name}}" (similar name, please verify)', { name: m.matched_on });
    case 'parent_company':
      return t('signals.matchParent', 'Names "{{name}}", which lists this supplier as its parent company', { name: m.matched_on });
    case 'country_exposure':
      return t('signals.matchCountry', 'Affects {{country}}, where this supplier is located', { country: m.matched_on });
    default:
      return m.match_type;
  }
}

function SignalRow({ m }: { m: SignalMatch }) {
  const { t } = useTranslation();
  const s = m.signal;
  return (
    <li className="py-3">
      <div className="flex items-center gap-2 flex-wrap">
        <SeverityBadge severity={s.severity} />
        <span className="text-[10px] font-bold uppercase text-gray-500 dark:text-gray-400">{s.source_label}</span>
        <span className="text-[10px] text-gray-400">
          {t('signals.published', 'Published {{date}}', { date: s.published_at })}
        </span>
      </div>
      <p className="text-sm font-medium text-gray-900 dark:text-white mt-1">{s.title}</p>
      <p className="text-xs text-gray-600 dark:text-gray-300 mt-0.5">{s.content}</p>
      <div className="flex items-center gap-3 mt-1">
        <span className="text-[10px] text-gray-500 dark:text-gray-400">{matchReason(m, t as any)}</span>
        {s.url && (
          <a href={s.url} target="_blank" rel="noopener noreferrer" className="text-[10px] text-blue-600 hover:underline">
            {t('signals.viewSource', 'View source record')}
          </a>
        )}
      </div>
    </li>
  );
}

export default function SupplierSignals({ supplierId }: { supplierId: string }) {
  const { t } = useTranslation();
  const [data, setData] = useState<SupplierSignalsData | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    setError('');
    api.getSupplierSignals(supplierId)
      .then(setData)
      .catch((err) => setError(err?.response?.status === 503
        ? t('signals.unavailable', 'Public signals are temporarily unavailable.')
        : t('signals.failed', 'Could not load public signals.')))
      .finally(() => setLoading(false));
  }, [supplierId, t]);

  if (loading) return <p className="text-sm text-gray-400 py-4">{t('signals.loading', 'Checking public records...')}</p>;
  if (error) return <p className="text-sm text-red-500 py-4">{error}</p>;
  if (!data) return null;

  return (
    <div className="space-y-4">
      <section>
        <h3 className="text-xs font-semibold uppercase text-gray-500 dark:text-gray-400">
          {t('signals.incidents', 'Records naming this supplier')} ({data.incidents.length})
        </h3>
        {data.incidents.length === 0 ? (
          <p className="text-xs text-gray-400 mt-2">
            {t('signals.noIncidents', 'No FDA recall or shortage records name this supplier. Add the names it trades under as aliases to widen the search.')}
          </p>
        ) : (
          <ul className="divide-y divide-gray-100 dark:divide-gray-700">
            {data.incidents.map((m) => <SignalRow key={m.signal.id} m={m} />)}
          </ul>
        )}
      </section>
      {data.exposures.length > 0 && (
        <section>
          <h3 className="text-xs font-semibold uppercase text-gray-500 dark:text-gray-400">
            {t('signals.exposures', 'Possible exposure: disasters in its country')} ({data.exposures.length})
          </h3>
          <p className="text-[10px] text-gray-400 mt-1">
            {t('signals.exposureNote', 'These alerts cover the whole country; they do not mean this supplier is affected.')}
          </p>
          <ul className="divide-y divide-gray-100 dark:divide-gray-700">
            {data.exposures.map((m) => <SignalRow key={m.signal.id} m={m} />)}
          </ul>
        </section>
      )}
    </div>
  );
}
