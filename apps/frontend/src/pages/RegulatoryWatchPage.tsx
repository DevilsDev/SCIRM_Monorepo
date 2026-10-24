import { FormEvent, useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '../contexts/AuthContext';
import { api, RegulatoryMatch, WatchlistItem } from '../services/api';
import SeverityBadge from '../components/SeverityBadge';

const input = 'px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm bg-white dark:bg-gray-800 dark:text-white';

function errorText(err: any, fallback: string): string {
  const detail = err?.response?.data?.detail;
  return typeof detail === 'string' ? detail : fallback;
}

/** The watched terms in a title, wrapped for highlighting (case-insensitive, whole words). */
export function highlightParts(text: string, terms: string[]): Array<{ text: string; hit: boolean }> {
  const words = terms.map((t) => t.trim()).filter(Boolean).map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  if (!words.length) return [{ text, hit: false }];
  const pattern = new RegExp(`\\b(${words.join('|')})\\b`, 'gi');
  const parts: Array<{ text: string; hit: boolean }> = [];
  let last = 0;
  for (const m of text.matchAll(pattern)) {
    if (m.index! > last) parts.push({ text: text.slice(last, m.index), hit: false });
    parts.push({ text: m[0], hit: true });
    last = m.index! + m[0].length;
  }
  if (last < text.length) parts.push({ text: text.slice(last), hit: false });
  return parts;
}

// Regulatory watch: FDA and EMA records (recalls, shortages, warning letters, import alerts,
// EMA shortages, safety communications, referrals) naming a substance or product on the
// organization's watchlist. Admins and analysts edit the list; everyone can read.
export default function RegulatoryWatchPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const canWrite = !!user?.roles?.some((r) => r === 'admin' || r === 'analyst');
  const [items, setItems] = useState<WatchlistItem[]>([]);
  const [matches, setMatches] = useState<RegulatoryMatch[]>([]);
  const [sources, setSources] = useState<Record<string, string>>({});
  const [days, setDays] = useState(180);
  const [source, setSource] = useState('');
  const [form, setForm] = useState({ kind: 'substance' as WatchlistItem['kind'], term: '', note: '' });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const loadItems = useCallback(() => api.listWatchlist().then((r) => setItems(r.items)).catch(() => setItems([])), []);
  const loadMatches = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.regulatoryWatch({ days, source });
      setMatches(r.matches);
      setSources(r.sources);
    } catch (err) {
      setError(errorText(err, t('rw.loadFailed', 'Could not load the regulatory records.')));
    } finally {
      setLoading(false);
    }
  }, [days, source, t]);
  useEffect(() => { loadItems(); }, [loadItems]);
  useEffect(() => { loadMatches(); }, [loadMatches, items]);

  const add = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    try {
      await api.addWatchlistItem(form);
      setForm((f) => ({ ...f, term: '', note: '' }));
      loadItems();
    } catch (err) {
      setError(errorText(err, t('rw.addFailed', 'The term could not be added.')));
    }
  };
  const remove = async (item: WatchlistItem) => {
    setError('');
    try { await api.deleteWatchlistItem(item.id); loadItems(); } catch (err) { setError(errorText(err, t('rw.removeFailed', 'The term could not be removed.'))); }
  };

  const terms = items.map((i) => i.term);
  return (
    <div className="p-6 max-w-7xl mx-auto">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{t('rw.title', 'Regulatory watch')}</h1>
      <p className="text-sm text-gray-500 mt-1">
        {t('rw.subtitle', 'FDA and EMA records that name a substance or product you watch: recalls, shortages, warning letters, import alerts, EMA shortages, safety communications (DHPCs) and referrals.')}
      </p>
      <div className="mt-6 grid grid-cols-1 lg:grid-cols-3 gap-6">
        <section className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-4">
          <h2 className="text-sm font-semibold text-gray-900 dark:text-white">{t('rw.watchlist', 'Watchlist')}</h2>
          <p className="text-xs text-gray-500 mt-1">{t('rw.howMatched', 'Matched as whole words, ignoring case: "metformin" matches "Metformin Hydrochloride Tablets". Use the names the regulators use (INN for substances).')}</p>
          {canWrite && (
            <form onSubmit={add} className="mt-3 space-y-2">
              <div className="flex gap-2">
                <select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value as WatchlistItem['kind'] })} className={input} aria-label={t('rw.kind', 'Kind')}>
                  <option value="substance">{t('rw.substance', 'Substance')}</option>
                  <option value="product">{t('rw.product', 'Product')}</option>
                </select>
                <input required minLength={3} maxLength={100} value={form.term} onChange={(e) => setForm({ ...form, term: e.target.value })}
                  placeholder={t('rw.termPlaceholder', 'e.g. rifampicin')} className={`${input} flex-1 min-w-0`} aria-label={t('rw.term', 'Term')} />
              </div>
              <input maxLength={300} value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })}
                placeholder={t('rw.notePlaceholder', 'Note (optional), e.g. which supplier or product line')} className={`${input} w-full`} />
              <button type="submit" className="px-3 py-1.5 rounded-lg text-sm font-medium bg-blue-600 text-white hover:bg-blue-700">{t('rw.add', 'Watch')}</button>
            </form>
          )}
          {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
          <ul className="mt-3 divide-y divide-gray-100 dark:divide-gray-700">
            {items.length === 0 && <li className="py-2 text-sm text-gray-500">{t('rw.empty', 'Nothing watched yet.')}</li>}
            {items.map((i) => (
              <li key={i.id} className="py-2 flex items-start justify-between gap-2 text-sm">
                <div>
                  <span className="text-gray-900 dark:text-white">{i.term}</span>
                  <span className="ml-2 text-xs text-gray-500">{i.kind === 'product' ? t('rw.product', 'Product') : t('rw.substance', 'Substance')}</span>
                  {i.note && <p className="text-xs text-gray-500">{i.note}</p>}
                </div>
                {canWrite && <button type="button" onClick={() => remove(i)} className="text-xs text-red-600 hover:underline">{t('rw.remove', 'Remove')}</button>}
              </li>
            ))}
          </ul>
        </section>
        <section className="lg:col-span-2">
          <div className="flex flex-wrap items-center gap-2 mb-3">
            <select value={days} onChange={(e) => setDays(Number(e.target.value))} className={input} aria-label={t('rw.period', 'Period')}>
              {[30, 90, 180, 365, 1095].map((d) => <option key={d} value={d}>{t('rw.lastDays', 'Last {{n}} days', { n: d })}</option>)}
            </select>
            <select value={source} onChange={(e) => setSource(e.target.value)} className={input} aria-label={t('rw.source', 'Source')}>
              <option value="">{t('rw.allSources', 'All FDA and EMA sources')}</option>
              {Object.entries(sources).map(([k, label]) => <option key={k} value={k}>{label}</option>)}
            </select>
            {loading && <span className="text-xs text-gray-500">{t('common.loading', 'Loading...')}</span>}
          </div>
          <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 divide-y divide-gray-100 dark:divide-gray-700">
            {matches.length === 0 ? (
              <p className="p-6 text-sm text-gray-500">{terms.length ? t('rw.noMatches', 'No records name a watched term in this period.') : t('rw.addTerms', 'Add substances or products to the watchlist to follow them here.')}</p>
            ) : matches.map((m) => (
              <article key={`${m.record.source}:${m.record.external_id}`} className="p-4">
                <div className="flex flex-wrap items-center gap-2 text-xs text-gray-500">
                  <span className="px-2 py-0.5 rounded-full bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-200">{m.source_label || m.record.source}</span>
                  <SeverityBadge severity={m.record.severity} />
                  <span>{t('rw.published', 'published {{d}}', { d: m.record.published_at })}</span>
                  {m.record.updated_at && m.record.updated_at !== m.record.published_at && <span>{t('rw.updated', 'updated {{d}}', { d: m.record.updated_at })}</span>}
                  <span>{t('rw.watching', 'watching: {{terms}}', { terms: m.terms.join(', ') })}</span>
                </div>
                <h3 className="mt-1 text-sm font-medium text-gray-900 dark:text-white">
                  {highlightParts(m.record.title, m.terms).map((p, i) => p.hit ? <mark key={i} className="bg-yellow-100 dark:bg-yellow-800/60 dark:text-white rounded px-0.5">{p.text}</mark> : <span key={i}>{p.text}</span>)}
                </h3>
                {m.record.summary && <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">{m.record.summary}</p>}
                {m.record.url && <a href={m.record.url} target="_blank" rel="noopener noreferrer" className="mt-1 inline-block text-xs text-blue-600 hover:underline">{t('rw.sourceRecord', 'Source record')}</a>}
              </article>
            ))}
          </div>
          <p className="mt-2 text-xs text-gray-500">{t('rw.disclaimer', 'Public records matched by wording, not findings about your suppliers; check the source record.')}</p>
        </section>
      </div>
    </div>
  );
}
