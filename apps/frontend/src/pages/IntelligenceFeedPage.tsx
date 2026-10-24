import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api, PublicSignal, PublicSourceStatus } from '../services/api';
import SeverityBadge from '../components/SeverityBadge';

const SOURCE_COLORS: Record<string, string> = {
  fda_recalls: 'bg-red-100 text-red-800',
  fda_shortages: 'bg-purple-100 text-purple-800',
  fda_warning_letters: 'bg-orange-100 text-orange-800',
  fda_import_alerts: 'bg-amber-100 text-amber-800',
  gdacs: 'bg-cyan-100 text-cyan-800',
  ema_shortages: 'bg-indigo-100 text-indigo-800',
  ema_dhpc: 'bg-blue-100 text-blue-800',
  ema_referrals: 'bg-sky-100 text-sky-800',
};

const STATUS_COLORS: Record<string, string> = {
  ok: 'text-green-600',
  error: 'text-red-600',
  rate_limited: 'text-orange-600',
  never_run: 'text-gray-400',
};

export default function IntelligenceFeedPage() {
  const [docs, setDocs] = useState<PublicSignal[]>([]);
  const [sources, setSources] = useState<Record<string, PublicSourceStatus>>({});
  const [loading, setLoading] = useState(true);
  const [sourceFilter, setSourceFilter] = useState('');
  const [ingesting, setIngesting] = useState(false);
  const [error, setError] = useState('');
  const { t } = useTranslation();

  const fetchSources = () => {
    api.getIntelligenceSources().then((data) => setSources(data.sources || {})).catch(() => setSources({}));
  };

  const fetchDocs = () => {
    setLoading(true);
    setError('');
    api.getIntelligenceFeed(sourceFilter || undefined)
      .then((data) => setDocs(data.documents || []))
      .catch(() => setError(t('intelligence.loadFailed', 'Could not load the intelligence feed.')))
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchDocs(); }, [sourceFilter]);
  useEffect(() => { fetchSources(); }, []);

  const handleIngest = async () => {
    setIngesting(true);
    try {
      await api.triggerIngestion();
    } catch {
      setError(t('intelligence.ingestFailed', 'Refreshing the sources failed.'));
    } finally {
      setIngesting(false);
      fetchSources();
      fetchDocs();
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{t('intelligence.title', 'Intelligence Feed')}</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">{t('intelligence.subtitlePublic', 'Public records from the FDA (recalls, shortages, warning letters, import alerts), the EMA (shortages, safety communications, referrals) and GDACS (disaster alerts), most recent first')}</p>
        </div>
        <button
          onClick={handleIngest}
          disabled={ingesting}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
        >
          {ingesting ? t('intelligence.ingesting', 'Ingesting...') : t('intelligence.refreshFeed', 'Refresh Feed')}
        </button>
      </div>

      {Object.keys(sources).length > 0 && (
        <div className="flex flex-wrap gap-4 text-xs">
          {Object.entries(sources).map(([key, s]) => (
            <span key={key} className="text-gray-500 dark:text-gray-400">
              {s.label}:{' '}
              <span className={`font-medium ${STATUS_COLORS[s.status] || ''}`}>
                {s.status === 'ok' && s.last_success_at
                  ? t('intelligence.updated', 'updated {{date}}', { date: new Date(s.last_success_at).toLocaleString() })
                  : s.status === 'never_run'
                    ? t('intelligence.neverRun', 'not fetched yet')
                    : `${s.status.replace('_', ' ')}${s.error ? ` (${s.error})` : ''}`}
              </span>
            </span>
          ))}
        </div>
      )}

      <div className="flex gap-2">
        {['', ...Object.keys(sources)].map((src) => (
          <button
            key={src}
            onClick={() => setSourceFilter(src)}
            className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${
              sourceFilter === src ? 'bg-blue-100 text-blue-800 border-blue-300' : 'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700'
            }`}
          >
            {src ? sources[src]?.label || src : t('intelligence.allSources', 'All Sources')}
          </button>
        ))}
      </div>

      {error && <p className="text-sm text-red-500">{error}</p>}

      {loading ? (
        <p className="text-sm text-gray-400">{t('intelligence.loading', 'Loading intelligence feed...')}</p>
      ) : docs.length === 0 ? (
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-8 text-center">
          <p className="text-sm text-gray-400">{t('intelligence.noPublicDocuments', 'No records from the last 30 days. Click "Refresh Feed" to fetch the public sources.')}</p>
        </div>
      ) : (
        <div className="space-y-3">
          {docs.map((doc) => (
            <div key={doc.id} className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-5">
              <div className="flex items-center gap-2 mb-1 flex-wrap">
                <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase ${SOURCE_COLORS[doc.source] || 'bg-gray-100 dark:bg-gray-700 text-gray-800'}`}>
                  {doc.source_label}
                </span>
                <SeverityBadge severity={doc.severity} />
                <span className="text-xs text-gray-400">{doc.region}</span>
              </div>
              <h3 className="text-sm font-semibold text-gray-900 dark:text-white mt-1">{doc.title}</h3>
              <p className="text-xs text-gray-600 dark:text-gray-300 mt-1 leading-relaxed">{doc.content}</p>
              <div className="flex items-center gap-3 mt-3 text-[10px] text-gray-400">
                <span>{t('signals.published', 'Published {{date}}', { date: doc.published_at })}</span>
                {doc.url && (
                  <a href={doc.url} target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline">
                    {t('signals.viewSource', 'View source record')}
                  </a>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
