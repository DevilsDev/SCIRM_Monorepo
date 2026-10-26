import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { api, WaterCatalog, WaterOverview, WaterSite } from '../services/api';
import { categoryClass, categoryRank, siteNote, SourceLine } from '../components/SupplierWaterRisk';

// Columns shown by default; every indicator can be chosen for sorting and filtering.
const COLUMNS = ['bws', 'bwd', 'drr', 'rfr', 'cfr'];

export function indicatorOf(site: WaterSite, key: string) {
  if (key.startsWith('future:')) {
    const [, scenario, year] = key.split(':');
    return site.future_water_stress?.find((f) => f.scenario === scenario && f.year === year);
  }
  return site.indicators?.find((i) => i.key === key);
}

/** Sites ordered by one indicator, highest WRI category first, then by supplier and site. */
export function sortSites(sites: WaterSite[], key: string): WaterSite[] {
  return [...sites].sort((a, b) =>
    categoryRank(indicatorOf(b, key)?.category) - categoryRank(indicatorOf(a, key)?.category)
    || (a.supplier || '').localeCompare(b.supplier || '') || (a.label || '').localeCompare(b.label || ''));
}

/** Sites whose category for the indicator is at least `min` (WRI's 0–4). */
export function atLeast(sites: WaterSite[], key: string, min: number): WaterSite[] {
  return sites.filter((s) => (indicatorOf(s, key)?.category ?? -9999) >= min);
}

export default function WaterRiskPage() {
  const { t } = useTranslation();
  const [data, setData] = useState<WaterOverview | null>(null);
  const [catalog, setCatalog] = useState<WaterCatalog | null>(null);
  const [error, setError] = useState('');
  const [sortKey, setSortKey] = useState('bws');
  const [minimum, setMinimum] = useState(-9999);

  useEffect(() => {
    Promise.all([api.waterOverview(), api.waterCatalog()])
      .then(([overview, cat]) => { setData(overview); setCatalog(cat); })
      .catch(() => setError(t('water.failed', 'Water risk could not be loaded.')));
  }, [t]);

  const options = useMemo(() => {
    if (!catalog) return [];
    return [
      ...catalog.indicators.map((i) => ({ key: i.key, label: i.name })),
      ...Object.keys(catalog.scenarios).flatMap((s) => Object.keys(catalog.years).map((y) => ({
        key: `future:${s}:20${y}`, label: `Water stress 20${y}, ${catalog.scenarios[s]}` }))),
    ];
  }, [catalog]);
  const rows = useMemo(() => (data ? sortSites(atLeast(data.sites, sortKey, minimum), sortKey) : []), [data, sortKey, minimum]);

  const download = async () => {
    try {
      const url = URL.createObjectURL(await api.waterExport());
      const a = document.createElement('a');
      a.href = url;
      a.download = 'scirm-water-risk.csv';
      a.click();
      URL.revokeObjectURL(url);
    } catch { setError(t('water.exportFailed', 'The CSV could not be downloaded.')); }
  };

  const nameOf = (key: string) => options.find((o) => o.key === key)?.label || key;
  const columns = COLUMNS.includes(sortKey) || !options.length ? COLUMNS : [...COLUMNS, sortKey];
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-gray-900 dark:text-white">{t('water.pageTitle', 'Water risk by site')}</h1>
          <p className="text-sm text-gray-600 dark:text-gray-300 max-w-3xl">
            {t('water.intro', 'WRI Aqueduct indicators for every located site of your active suppliers, each shown on its own with WRI\'s category. SCIRM does not combine them into a score. Sites are looked up offline; no coordinates leave SCIRM.')}
          </p>
        </div>
        <button type="button" onClick={download} disabled={!data?.sites.length}
          className="px-3 py-1.5 text-sm rounded bg-blue-600 text-white disabled:opacity-50">
          {t('water.download', 'Download CSV')}
        </button>
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}
      {!data && !error && <p className="text-sm text-gray-500">{t('common.loading', 'Loading…')}</p>}
      {data && catalog && (
        <>
          <div className="flex flex-wrap items-end gap-3 text-sm">
            <label className="flex flex-col">
              <span className="text-xs text-gray-500">{t('water.sortBy', 'Sort by')}</span>
              <select value={sortKey} onChange={(e) => setSortKey(e.target.value)}
                className="px-2 py-1 border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800">
                {options.map((o) => <option key={o.key} value={o.key}>{o.label}</option>)}
              </select>
            </label>
            <label className="flex flex-col">
              <span className="text-xs text-gray-500">{t('water.show', 'Show')}</span>
              <select value={minimum} onChange={(e) => setMinimum(Number(e.target.value))}
                className="px-2 py-1 border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800">
                <option value={-9999}>{t('water.all', 'All sites')}</option>
                <option value={3}>{t('water.high', 'High or extremely high for this indicator')}</option>
                <option value={4}>{t('water.extreme', 'Extremely high for this indicator')}</option>
              </select>
            </label>
            <span className="text-xs text-gray-500">
              {t('water.count', '{{shown}} of {{total}} sites', { shown: rows.length, total: data.sites.length })}
            </span>
          </div>
          {catalog.indicators.find((i) => i.key === sortKey) && (
            <p className="text-xs text-gray-500">{catalog.indicators.find((i) => i.key === sortKey)?.about}</p>
          )}
          {data.sites.length === 0 ? (
            <p className="text-sm text-gray-600 dark:text-gray-300">
              {t('water.empty', 'No supplier has a located site yet. Add sites in the supplier panel (Suppliers, then a supplier, then Sites).')}
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full text-xs">
                <thead>
                  <tr className="text-left text-gray-500 border-b border-gray-200 dark:border-gray-700">
                    <th className="py-1.5 pr-2">{t('water.supplier', 'Supplier')}</th>
                    <th className="py-1.5 pr-2">{t('water.site', 'Site')}</th>
                    {columns.map((k) => <th key={k} className="py-1.5 pr-2">{nameOf(k)}</th>)}
                    <th className="py-1.5 pr-2">{t('water.stress2050', 'Water stress 2050 (business as usual)')}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                  {rows.map((s) => {
                    const note = siteNote(s);
                    const future = indicatorOf(s, 'future:bau:2050');
                    return (
                      <tr key={`${s.supplier_id}-${s.id}`} className="align-top">
                        <td className="py-1.5 pr-2 text-gray-900 dark:text-white">{s.supplier}</td>
                        <td className="py-1.5 pr-2">
                          <div>{s.label}</div>
                          <div className="text-gray-500">{[s.province, s.unit_country].filter(Boolean).join(', ')}</div>
                          {note && <div className="text-[11px] text-amber-700 dark:text-amber-300 max-w-xs">{note}</div>}
                        </td>
                        {columns.map((k) => {
                          const v = indicatorOf(s, k);
                          return (
                            <td key={k} className="py-1.5 pr-2">
                              <span className={`px-1.5 py-0.5 rounded ${categoryClass(v?.category)}`}>{v?.label || 'No data'}</span>
                            </td>
                          );
                        })}
                        <td className="py-1.5 pr-2">
                          <span className={`px-1.5 py-0.5 rounded ${categoryClass(future?.category)}`}>{future?.label || 'No data'}</span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
          {data.suppliers_without_located_site.length > 0 && (
            <div>
              <h2 className="text-sm font-semibold text-gray-900 dark:text-white">
                {t('water.unknown', 'Unknown: suppliers without a located site ({{n}})', { n: data.suppliers_without_located_site.length })}
              </h2>
              <p className="text-xs text-gray-500 mb-1">
                {t('water.unknownHint', 'Their water risk is not known here. It is not low. Add a site with a city or coordinates in the supplier panel.')}
              </p>
              <p className="text-xs text-gray-700 dark:text-gray-300">
                {data.suppliers_without_located_site.map((u) => u.name).join(' · ')}{' '}
                <Link to="/suppliers" className="text-blue-600 hover:underline">{t('water.toSuppliers', 'Go to suppliers')}</Link>
              </p>
            </div>
          )}
          <SourceLine source={data.source} />
          <p className="text-[11px] text-gray-500">{data.source.citation}</p>
        </>
      )}
    </div>
  );
}
