import { FormEvent, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '../contexts/AuthContext';
import { api, Supplier, SupplierSite } from '../services/api';

function precisionLabel(site: SupplierSite, t: (k: string, f: string) => string): string {
  if (site.precision === 'exact') return t('sites.exact', 'exact coordinates');
  if (site.precision === 'city_ambiguous') return t('sites.ambiguous', 'city level; several places share this name, enter coordinates to be sure');
  return t('sites.city', 'city level');
}

// Places the supplier operates. Disaster alerts are matched to these sites by distance;
// without any, a disaster anywhere in the supplier's country counts as possible exposure.
export default function SupplierSites({ supplier, onChange }: { supplier: Supplier; onChange: (s: Supplier) => void }) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const canEdit = !!user?.roles?.some((r) => r === 'admin' || r === 'analyst');
  const [label, setLabel] = useState('');
  const [city, setCity] = useState('');
  const [country, setCountry] = useState(supplier.country_code || '');
  const [lat, setLat] = useState('');
  const [lon, setLon] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const sites = supplier.sites || [];

  const add = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    setBusy(true);
    try {
      const coords = lat && lon ? { lat: Number(lat), lon: Number(lon) } : {};
      onChange(await api.addSupplierSite(supplier.id, { label: label.trim(), country: country.trim().toUpperCase(),
        city: city.trim() || undefined, ...coords }));
      setLabel(''); setCity(''); setLat(''); setLon('');
    } catch (err: any) {
      setError(err?.response?.data?.detail || t('sites.addFailed', 'Could not add the site.'));
    } finally {
      setBusy(false);
    }
  };

  const remove = async (site: SupplierSite) => {
    setError('');
    try {
      onChange(await api.removeSupplierSite(supplier.id, site.id));
    } catch (err: any) {
      setError(err?.response?.data?.detail || t('sites.removeFailed', 'Could not remove the site.'));
    }
  };

  const input = 'px-2 py-1 border border-gray-300 dark:border-gray-600 rounded text-xs bg-white dark:bg-gray-800';
  return (
    <div className="space-y-2">
      <p className="text-[11px] text-gray-500 dark:text-gray-400">
        {sites.length
          ? t('sites.hint', 'Disaster alerts are matched to these sites by distance from the alert\'s reported location.')
          : t('sites.none', 'No sites yet, so a disaster anywhere in the supplier\'s country counts as possible exposure. Add plants or warehouses to narrow it down.')}
      </p>
      {sites.length > 0 && (
        <ul className="divide-y divide-gray-100 dark:divide-gray-700 text-xs">
          {sites.map((s) => (
            <li key={s.id} className="py-1.5 flex items-center justify-between gap-2">
              <span>
                <span className="font-medium text-gray-900 dark:text-white">{s.label}</span>
                <span className="text-gray-500"> · {[s.city, s.country].filter(Boolean).join(', ')} · {precisionLabel(s, t as any)}
                  {s.source === 'sap_lfa1' && ` · ${t('sites.fromSap', 'from SAP')}`}</span>
              </span>
              {canEdit && (
                <button type="button" onClick={() => remove(s)} className="text-red-600 hover:underline">
                  {t('sites.remove', 'Remove')}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {canEdit && (
        <form onSubmit={add} className="flex flex-wrap gap-1.5 items-end">
          <input className={`${input} w-32`} placeholder={t('sites.label', 'Name, e.g. Plant 2')} value={label}
            onChange={(e) => setLabel(e.target.value)} required maxLength={100} aria-label={t('sites.labelAria', 'Site name')} />
          <input className={`${input} w-28`} placeholder={t('sites.cityPh', 'City')} value={city}
            onChange={(e) => setCity(e.target.value)} maxLength={100} aria-label={t('sites.cityAria', 'City')} />
          <input className={`${input} w-12 uppercase`} placeholder="DE" value={country}
            onChange={(e) => setCountry(e.target.value)} required maxLength={2} aria-label={t('sites.countryAria', 'Country code')} />
          <input className={`${input} w-20`} placeholder={t('sites.lat', 'Latitude')} value={lat} inputMode="decimal"
            onChange={(e) => setLat(e.target.value)} aria-label={t('sites.lat', 'Latitude')} />
          <input className={`${input} w-20`} placeholder={t('sites.lon', 'Longitude')} value={lon} inputMode="decimal"
            onChange={(e) => setLon(e.target.value)} aria-label={t('sites.lon', 'Longitude')} />
          <button type="submit" disabled={busy || !label.trim() || country.trim().length !== 2 || (!city.trim() && !(lat && lon))}
            className="px-2 py-1 bg-blue-600 text-white rounded text-xs disabled:opacity-50">
            {t('sites.add', 'Add site')}
          </button>
        </form>
      )}
      {error && <p className="text-xs text-red-600">{error}</p>}
    </div>
  );
}
