import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api, WaterSite, WaterSource } from '../services/api';

// WRI's categories: 0 low to 4 extremely high; -1 a special class such as "Arid and Low
// Water Use" or "No Risk"; -9999 (or nothing) no data. The colours follow WRI's order and
// add nothing to it: SCIRM has no water score of its own.
export function categoryClass(category: number | null | undefined): string {
  switch (category) {
    case 4: return 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-200';
    case 3: return 'bg-orange-100 text-orange-800 dark:bg-orange-900/40 dark:text-orange-200';
    case 2: return 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200';
    case 1: return 'bg-yellow-50 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-200';
    case 0: return 'bg-green-50 text-green-800 dark:bg-green-900/30 dark:text-green-200';
    case -1: return 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-200';
    default: return 'bg-white text-gray-500 border border-dashed border-gray-300 dark:bg-gray-800 dark:text-gray-400 dark:border-gray-600';
  }
}

/** Sort key: highest WRI category first, then special classes, then no data. */
export function categoryRank(category: number | null | undefined): number {
  if (category === null || category === undefined || category < -1) return -2;
  return category;
}

/** What the person needs to know about how a site was placed, or '' when nothing. */
export function siteNote(site: WaterSite): string {
  const notes: string[] = [];
  if (site.status === 'nearest') notes.push(`no Aqueduct area at the exact point; nearest one ${site.distance_km} km away`);
  if (site.precision && site.precision !== 'exact') notes.push('placed at the city centre, which can lie in a different river basin from the plant');
  if (site.near_boundary) notes.push('close to a boundary with different values; check the WRI atlas for the exact location');
  return notes.join('; ');
}

export function SourceLine({ source }: { source: WaterSource }) {
  return (
    <p className="text-[11px] text-gray-500 dark:text-gray-400">
      Source: <a className="underline" href={source.url} target="_blank" rel="noreferrer">{source.name}</a>, baseline
      {' '}{source.baseline}, licensed <a className="underline" href={source.licence_url} target="_blank" rel="noreferrer">{source.licence}</a>.
      {' '}Categories and labels are WRI's own. WRI notes that its indicators are modelled and have not been validated.
    </p>
  );
}

const MAIN = ['bws', 'bwd', 'drr', 'rfr', 'cfr', 'gtd'];

// Water risk for each of the supplier's sites, from WRI Aqueduct 4.0, looked up offline.
export default function SupplierWaterRisk({ supplierId }: { supplierId: string }) {
  const { t } = useTranslation();
  const [sites, setSites] = useState<WaterSite[] | null>(null);
  const [source, setSource] = useState<WaterSource | null>(null);
  const [error, setError] = useState('');
  const [open, setOpen] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setSites(null);
    setError('');
    api.waterSupplier(supplierId)
      .then((r) => { if (live) { setSites(r.sites); setSource(r.source); } })
      .catch(() => { if (live) setError(t('water.failed', 'Water risk could not be loaded.')); });
    return () => { live = false; };
  }, [supplierId, t]);

  if (error) return <p className="text-xs text-red-600">{error}</p>;
  if (!sites) return <p className="text-xs text-gray-500">{t('common.loading', 'Loading…')}</p>;
  const located = sites.filter((s) => s.status === 'inside' || s.status === 'nearest');
  return (
    <div className="space-y-2">
      {!located.length && (
        <p className="text-[11px] text-gray-500 dark:text-gray-400">
          {t('water.noSites', 'No located site, so water risk is unknown for this supplier, not low. Add a site with a city or coordinates.')}
        </p>
      )}
      {sites.filter((s) => s.status === 'outside').map((s) => (
        <p key={s.id} className="text-[11px] text-gray-500">{s.label}: {t('water.outside', 'no Aqueduct area within reach of these coordinates (open water?). Check them.')}</p>
      ))}
      {located.map((s) => {
        const key = s.id || s.label || '';
        const note = siteNote(s);
        return (
          <div key={key} className="text-xs">
            <div className="flex items-baseline justify-between gap-2">
              <span>
                <span className="font-medium text-gray-900 dark:text-white">{s.label}</span>
                <span className="text-gray-500"> · {[s.province, s.unit_country].filter(Boolean).join(', ')} · basin {s.basin}</span>
              </span>
              <button type="button" className="text-blue-600 hover:underline" onClick={() => setOpen(open === key ? null : key)}>
                {open === key ? t('water.less', 'Fewer indicators') : t('water.more', 'All indicators')}
              </button>
            </div>
            {note && <p className="text-[11px] text-amber-700 dark:text-amber-300">{note}</p>}
            <ul className="mt-1 flex flex-wrap gap-1">
              {(s.indicators || []).filter((i) => open === key || MAIN.includes(i.key)).map((i) => (
                <li key={i.key} className={`px-1.5 py-0.5 rounded ${categoryClass(i.category)}`} title={i.raw === null ? '' : `raw value ${i.raw}`}>
                  {i.name}: {i.label}
                </li>
              ))}
            </ul>
            <p className="mt-1 text-[11px] text-gray-600 dark:text-gray-300">
              {t('water.future', 'Projected water stress (business as usual):')}{' '}
              {(s.future_water_stress || []).filter((f) => f.scenario === 'bau').map((f) => `${f.year} ${f.label}`).join(' · ')}
            </p>
            {open === key && (
              <p className="text-[11px] text-gray-500">
                {(s.future_water_stress || []).filter((f) => f.scenario !== 'bau').map((f) => `${f.scenario_label} ${f.year}: ${f.label}`).join(' · ')}
              </p>
            )}
          </div>
        );
      })}
      {source && <SourceLine source={source} />}
    </div>
  );
}
