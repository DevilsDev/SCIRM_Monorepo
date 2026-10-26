import { FormEvent, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '../contexts/AuthContext';
import { api, GleifSource, LeiEntity, OwnershipLink, ParentLevel } from '../services/api';

function errorText(err: any, fallback: string): string {
  return err?.response?.data?.detail || fallback;
}

export function place(e: Pick<LeiEntity, 'legal_address'>): string {
  return [e.legal_address?.city, e.legal_address?.country].filter(Boolean).join(', ');
}

/** One parent level in words: the parent, GLEIF's exception reason, or unknown. */
export function parentText(level: ParentLevel): string {
  if (level.kind === 'parent') return `${level.legal_name} (${place(level)})`;
  return level.explanation;
}

/** Statuses worth a warning: a lapsed or retired LEI, or an entity that is no longer active. */
export function statusWarning(e: LeiEntity): string {
  const notes: string[] = [];
  if (e.registration_status && e.registration_status !== 'ISSUED') notes.push(`LEI registration is ${e.registration_status.toLowerCase()}, so the data may be out of date`);
  if (e.entity_status && e.entity_status !== 'ACTIVE') notes.push(`GLEIF lists the entity as ${e.entity_status.toLowerCase()}`);
  return notes.join('; ');
}

export function GleifSourceLine({ source }: { source: GleifSource }) {
  return (
    <p className="text-[11px] text-gray-500 dark:text-gray-400">
      Source: <a className="underline" href={source.url} target="_blank" rel="noreferrer">{source.name}</a>, licensed
      {' '}<a className="underline" href={source.licence_url} target="_blank" rel="noreferrer">{source.licence}</a>. {source.note}
    </p>
  );
}

function Parent({ label, level }: { label: string; level: ParentLevel }) {
  return (
    <p>
      <span className="text-gray-500">{label}: </span>
      {level.kind === 'parent'
        ? <a className="text-blue-600 hover:underline" href={level.url} target="_blank" rel="noreferrer">{parentText(level)}</a>
        : <span className={level.kind === 'not_reported' ? 'italic text-gray-500' : 'text-gray-700 dark:text-gray-300'}>{parentText(level)}</span>}
    </p>
  );
}

// Who owns the supplier, per GLEIF. A person picks the supplier's LEI from search results;
// SCIRM never links one by itself.
export default function SupplierOwnership({ supplierId }: { supplierId: string }) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const canEdit = !!user?.roles?.some((r) => r === 'admin' || r === 'analyst');
  const [link, setLink] = useState<OwnershipLink | null | undefined>(undefined);
  const [source, setSource] = useState<GleifSource | null>(null);
  const [name, setName] = useState('');
  const [country, setCountry] = useState('');
  const [candidates, setCandidates] = useState<LeiEntity[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let live = true;
    setLink(undefined); setCandidates(null); setError('');
    api.supplierOwnership(supplierId).then((r) => {
      if (!live) return;
      setLink(r.link); setSource(r.source);
      setName(r.supplier.name || ''); setCountry(r.supplier.country_code?.slice(0, 2) || '');
    }).catch(() => { if (live) setError(t('own.failed', 'Ownership could not be loaded.')); });
    return () => { live = false; };
  }, [supplierId, t]);

  const act = async (fn: () => Promise<void>) => {
    setError(''); setBusy(true);
    try { await fn(); } catch (err) { setError(errorText(err, t('own.actionFailed', 'That did not work.'))); } finally { setBusy(false); }
  };
  const search = (e: FormEvent) => {
    e.preventDefault();
    act(async () => setCandidates((await api.ownershipSearch(name.trim(), country.trim())).candidates));
  };

  if (link === undefined) return error ? <p className="text-xs text-red-600">{error}</p> : <p className="text-xs text-gray-500">{t('common.loading', 'Loading…')}</p>;
  const input = 'px-2 py-1 border border-gray-300 dark:border-gray-600 rounded text-xs bg-white dark:bg-gray-800';
  return (
    <div className="space-y-2 text-xs">
      {link ? (
        <div className="space-y-1">
          <p>
            <a className="font-medium text-blue-600 hover:underline" href={link.snapshot.entity.url} target="_blank" rel="noreferrer">
              {link.snapshot.entity.legal_name}</a>
            <span className="text-gray-500"> · LEI {link.lei} · {place(link.snapshot.entity)}</span>
          </p>
          {statusWarning(link.snapshot.entity) && <p className="text-amber-700 dark:text-amber-300">{statusWarning(link.snapshot.entity)}</p>}
          <Parent label={t('own.direct', 'Direct parent')} level={link.snapshot.direct_parent} />
          <Parent label={t('own.ultimate', 'Ultimate parent')} level={link.snapshot.ultimate_parent} />
          <p className="text-[11px] text-gray-500">
            {t('own.confirmed', 'Linked by {{who}} on {{when}}; read from GLEIF {{read}}.', {
              who: link.confirmed_by, when: link.confirmed_at.slice(0, 10), read: link.refreshed_at.slice(0, 10) })}
          </p>
          {canEdit && (
            <div className="flex gap-3">
              <button type="button" disabled={busy} className="text-blue-600 hover:underline disabled:opacity-50"
                onClick={() => act(async () => setLink(await api.refreshOwnership(supplierId)))}>{t('own.refresh', 'Refresh from GLEIF')}</button>
              <button type="button" disabled={busy} className="text-red-600 hover:underline disabled:opacity-50"
                onClick={() => act(async () => { await api.unlinkOwnership(supplierId); setLink(null); })}>{t('own.unlink', 'Remove link')}</button>
            </div>
          )}
        </div>
      ) : (
        <p className="text-[11px] text-gray-500 dark:text-gray-400">
          {t('own.none', 'No LEI confirmed, so ownership is unknown here. Many smaller suppliers have no LEI.')}
        </p>
      )}
      {!link && canEdit && (
        <>
          <form onSubmit={search} className="flex flex-wrap gap-1.5 items-end">
            <input className={`${input} w-56`} value={name} onChange={(e) => setName(e.target.value)} maxLength={200}
              placeholder={t('own.namePh', 'Legal name or LEI')} aria-label={t('own.nameAria', 'Legal name or LEI')} />
            <input className={`${input} w-12 uppercase`} value={country} onChange={(e) => setCountry(e.target.value)} maxLength={2}
              placeholder="DE" aria-label={t('own.countryAria', 'Country code (optional)')} />
            <button type="submit" disabled={busy || name.trim().length < 2} className="px-2 py-1 bg-blue-600 text-white rounded disabled:opacity-50">
              {t('own.search', 'Search GLEIF')}
            </button>
          </form>
          <p className="text-[11px] text-gray-500">{t('own.searchNote', 'The name and country you enter are sent to GLEIF to search.')}</p>
          {candidates && (candidates.length === 0
            ? <p className="text-gray-500">{t('own.noneFound', 'No LEI found. That leaves ownership unknown; it does not mean the supplier is independent.')}</p>
            : (
              <ul className="divide-y divide-gray-100 dark:divide-gray-700">
                {candidates.map((c) => (
                  <li key={c.lei} className="py-1.5 flex items-start justify-between gap-2">
                    <span>
                      <a className="font-medium text-gray-900 dark:text-white hover:underline" href={c.url} target="_blank" rel="noreferrer">{c.legal_name}</a>
                      <span className="text-gray-500"> · {place(c)} · LEI {c.lei} · {c.registration_status?.toLowerCase()}</span>
                    </span>
                    <button type="button" disabled={busy} className="shrink-0 text-blue-600 hover:underline disabled:opacity-50"
                      onClick={() => act(async () => { setLink(await api.linkOwnership(supplierId, c.lei)); setCandidates(null); })}>
                      {t('own.confirm', 'This is the supplier')}
                    </button>
                  </li>
                ))}
              </ul>
            ))}
        </>
      )}
      {error && <p className="text-red-600">{error}</p>}
      {source && <GleifSourceLine source={source} />}
    </div>
  );
}
