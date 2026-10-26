import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { api, OwnershipOverview } from '../services/api';
import { GleifSourceLine, parentText, place, statusWarning } from '../components/SupplierOwnership';

/** "3 of 10 active suppliers have a confirmed LEI." Inactive linked suppliers are not counted. */
export function coverage(data: Pick<OwnershipOverview, 'links' | 'unlinked'>): { linked: number; active: number } {
  const linked = data.links.filter((l) => l.is_active).length;
  return { linked, active: linked + data.unlinked.length };
}

export default function OwnershipPage() {
  const { t } = useTranslation();
  const [data, setData] = useState<OwnershipOverview | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    api.ownershipOverview().then(setData).catch(() => setError(t('own.failed', 'Ownership could not be loaded.')));
  }, [t]);

  const cov = data ? coverage(data) : null;
  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-gray-900 dark:text-white">{t('own.pageTitle', 'Ownership')}</h1>
        <p className="text-sm text-gray-600 dark:text-gray-300 max-w-3xl">
          {t('own.intro', 'Who owns your suppliers, as reported to the Global LEI Index (GLEIF): each supplier\'s direct and ultimate accounting consolidating parent. Suppliers that share an owner are grouped, so a hidden dependency on one group shows. Link a supplier to its LEI in the supplier panel.')}
        </p>
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}
      {!data && !error && <p className="text-sm text-gray-500">{t('common.loading', 'Loading…')}</p>}
      {data && cov && (
        <>
          <p className="text-sm text-gray-700 dark:text-gray-300">
            {t('own.coverage', '{{linked}} of {{active}} active suppliers have a confirmed LEI.', cov)}
          </p>
          <section>
            <h2 className="text-sm font-semibold text-gray-900 dark:text-white mb-1">{t('own.shared', 'Suppliers that share an owner')}</h2>
            {data.shared_owners.length === 0 ? (
              <p className="text-xs text-gray-500">
                {t('own.noShared', 'None among the linked suppliers. Suppliers whose parents are not reported or are withheld can still share an owner that GLEIF does not show.')}
              </p>
            ) : (
              <ul className="space-y-2">
                {data.shared_owners.map((g) => (
                  <li key={g.owner_lei} className="text-xs border border-gray-200 dark:border-gray-700 rounded p-2">
                    <p>
                      <a className="font-medium text-blue-600 hover:underline" href={g.owner_url || '#'} target="_blank" rel="noreferrer">{g.owner_name}</a>
                      <span className="text-gray-500"> · {g.owner_country} · LEI {g.owner_lei} · {t('own.suppliersN', '{{n}} suppliers', { n: g.suppliers.length })}</span>
                    </p>
                    <p className="text-gray-700 dark:text-gray-300">
                      {g.suppliers.map((s) => `${s.supplier}${s.relation === 'is the owner' ? ' (the owner itself)' : ''}`).join(' · ')}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </section>
          <section>
            <h2 className="text-sm font-semibold text-gray-900 dark:text-white mb-1">{t('own.linked', 'Linked suppliers')}</h2>
            {data.links.length === 0 ? (
              <p className="text-xs text-gray-500">{t('own.noneLinked', 'No supplier is linked to an LEI yet.')}</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full text-xs">
                  <thead>
                    <tr className="text-left text-gray-500 border-b border-gray-200 dark:border-gray-700">
                      <th className="py-1.5 pr-2">{t('own.supplier', 'Supplier')}</th>
                      <th className="py-1.5 pr-2">{t('own.entity', 'Legal entity (LEI)')}</th>
                      <th className="py-1.5 pr-2">{t('own.direct', 'Direct parent')}</th>
                      <th className="py-1.5 pr-2">{t('own.ultimate', 'Ultimate parent')}</th>
                      <th className="py-1.5 pr-2">{t('own.read', 'Read from GLEIF')}</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                    {data.links.map((l) => (
                      <tr key={l.supplier_id} className="align-top">
                        <td className="py-1.5 pr-2 text-gray-900 dark:text-white">{l.supplier}{!l.is_active && <span className="text-gray-500"> (inactive)</span>}</td>
                        <td className="py-1.5 pr-2">
                          <a className="text-blue-600 hover:underline" href={l.snapshot.entity.url} target="_blank" rel="noreferrer">{l.snapshot.entity.legal_name}</a>
                          <div className="text-gray-500">{place(l.snapshot.entity)} · {l.lei}</div>
                          {statusWarning(l.snapshot.entity) && <div className="text-amber-700 dark:text-amber-300">{statusWarning(l.snapshot.entity)}</div>}
                        </td>
                        <td className="py-1.5 pr-2 max-w-xs">{parentText(l.snapshot.direct_parent)}</td>
                        <td className="py-1.5 pr-2 max-w-xs">{parentText(l.snapshot.ultimate_parent)}</td>
                        <td className="py-1.5 pr-2 text-gray-500">{l.refreshed_at.slice(0, 10)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
          {data.unlinked.length > 0 && (
            <section>
              <h2 className="text-sm font-semibold text-gray-900 dark:text-white">
                {t('own.unknown', 'Unknown: active suppliers without a confirmed LEI ({{n}})', { n: data.unlinked.length })}
              </h2>
              <p className="text-xs text-gray-700 dark:text-gray-300">
                {data.unlinked.map((u) => u.name).join(' · ')}{' '}
                <Link to="/suppliers" className="text-blue-600 hover:underline">{t('own.toSuppliers', 'Go to suppliers')}</Link>
              </p>
            </section>
          )}
          <GleifSourceLine source={data.source} />
        </>
      )}
    </div>
  );
}
