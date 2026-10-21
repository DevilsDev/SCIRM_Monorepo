import { ChangeEvent, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api, SapSpendResult } from '../services/api';
import { decodeExport, headerCells } from '../services/fileText';

const MAX_BYTES = 100_000_000;
const FIELDS: Array<{ field: string; column: string; label: string }> = [
  { field: 'number', column: 'LIFNR', label: 'Supplier number' },
  { field: 'date', column: 'BEDAT', label: 'Order date' },
  { field: 'amount', column: 'NETWR', label: 'Net value' },
  { field: 'currency', column: 'WAERS', label: 'Currency' },
  { field: 'document', column: 'EBELN', label: 'Order number' },
  { field: 'deletion_flag', column: 'LOEKZ', label: 'Deletion flag' },
];

export function formatSpend(amount: string | undefined, currency: string | null | undefined): string {
  if (amount === undefined || !currency) return '–';
  try {
    return new Intl.NumberFormat(undefined, { style: 'currency', currency, maximumFractionDigits: 0 }).format(Number(amount));
  } catch {
    return `${Math.round(Number(amount)).toLocaleString()} ${currency}`;
  }
}

// Purchase-order spend per supplier for the last 12 months, from an SAP export or, when
// the organization has an SAP connection, read from SAP directly.
export default function SapSpendImport({ connected = false }: { connected?: boolean }) {
  const { t } = useTranslation();
  const [content, setContent] = useState('');
  const [headers, setHeaders] = useState<string[]>([]);
  const [columnMap, setColumnMap] = useState<Record<string, string>>({});
  const [decimal, setDecimal] = useState<'' | '.' | ','>('');
  const [preview, setPreview] = useState<SapSpendResult | null>(null);
  const [done, setDone] = useState<SapSpendResult | null>(null);
  const [stale, setStale] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  // Which source the current preview came from; applying uses the same one.
  const [fromSap, setFromSap] = useState(false);
  const technical = headers.some((h) => h.toUpperCase() === 'LIFNR');

  const onFile = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setPreview(null);
    setDone(null);
    setError('');
    if (file.size > MAX_BYTES) {
      setError(t('spend.tooBig', 'The file is larger than 100 MB. Export a shorter period.'));
      return;
    }
    const text = decodeExport(new Uint8Array(await file.arrayBuffer()));
    setContent(text);
    setHeaders(headerCells(text));
    setColumnMap({});
  };

  const run = async (apply: boolean, sap = fromSap) => {
    setBusy(true);
    setError('');
    setFromSap(sap);
    try {
      const result = sap
        ? await api.importSapSpendFromConnection({ apply })
        : await api.importSapSpend({
          content, apply, decimal: decimal || undefined,
          column_map: Object.fromEntries(Object.entries(columnMap).filter(([, v]) => v)),
        });
      if (apply) { setDone(result); setPreview(null); } else { setPreview(result); setStale(false); }
    } catch (err: any) {
      setError(err?.response?.data?.detail || t('spend.failed', 'The import failed. Try again in a moment.'));
    } finally {
      setBusy(false);
    }
  };

  const change = (update: () => void) => { update(); if (preview) setStale(true); };
  const card = 'bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6';

  return (
    <div className={card}>
      <h2 className="text-lg font-semibold text-gray-900 dark:text-white">{t('spend.title', 'Purchase-order spend')}</h2>
      <p className="text-sm text-gray-500 dark:text-gray-400 mt-1 mb-3">
        {t('spend.intro', 'Upload purchase-order items (EKPO with EKKO, or an ME2N/ME2L list) to rank suppliers by the last 12 months of spend. Import the supplier master first. Each upload replaces earlier spend; currencies are never converted.')}
      </p>
      <input type="file" accept=".txt,.csv,.tsv,text/plain,text/csv" onChange={onFile} className="text-sm" />
      <p className="text-xs text-gray-500 mt-2">
        {t('spend.columns', 'Columns used: LIFNR, BEDAT, NETWR, WAERS (required); EBELN, WERKS, LOEKZ (optional).')}
      </p>
      <div className="flex flex-wrap items-center gap-3 mt-3 text-xs text-gray-700 dark:text-gray-300">
        <label className="flex items-center gap-2">
          {t('spend.decimal', 'Decimal separator')}
          <select value={decimal} onChange={(e) => change(() => setDecimal(e.target.value as '' | '.' | ','))}
            className="px-2 py-1 border rounded bg-white dark:bg-gray-800">
            <option value="">{t('spend.decimalAuto', 'Detect')}</option>
            <option value=",">{t('spend.decimalComma', 'Comma (1.234,56)')}</option>
            <option value=".">{t('spend.decimalPoint', 'Point (1,234.56)')}</option>
          </select>
        </label>
      </div>
      {content && headers.length > 0 && !technical && (
        <div className="mt-3 border border-amber-300 bg-amber-50 rounded-lg p-3 grid grid-cols-1 sm:grid-cols-2 gap-2">
          {FIELDS.map((f) => (
            <label key={f.field} className="text-xs text-gray-700 flex items-center gap-2">
              <span className="w-36">{f.label} ({f.column})</span>
              <select value={columnMap[f.field] || ''} className="flex-1 px-2 py-1 border rounded text-xs bg-white"
                onChange={(e) => change(() => setColumnMap({ ...columnMap, [f.field]: e.target.value }))}>
                <option value="">{t('sap.notInFile', '(not in file)')}</option>
                {headers.map((h) => <option key={h} value={h}>{h}</option>)}
              </select>
            </label>
          ))}
        </div>
      )}
      <div className="flex flex-wrap gap-2 mt-4">
        <button type="button" disabled={!content || busy} onClick={() => run(false, false)}
          className="px-4 py-2 rounded-lg text-sm font-medium bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50">
          {busy && !fromSap ? t('sap.working', 'Working...') : preview && !fromSap ? t('sap.updatePreview', 'Update preview') : t('spend.previewFile', 'Preview the file')}
        </button>
        {connected && (
          <button type="button" disabled={busy} onClick={() => run(false, true)}
            className="px-4 py-2 rounded-lg text-sm font-medium border border-blue-600 text-blue-700 hover:bg-blue-50 disabled:opacity-50">
            {busy && fromSap ? t('sap.reading', 'Reading from SAP...') : t('spend.previewSap', 'Preview the last 12 months from SAP')}
          </button>
        )}
      </div>
      {error && <p className="text-sm text-red-600 mt-3">{error}</p>}

      {preview && (
        <div className="mt-4 space-y-3 text-sm">
          {preview.period ? (
            <p className="text-gray-700 dark:text-gray-300">
              {t('spend.period', 'Period {{from}} to {{to}}: {{counted}} order lines counted ({{deleted}} deleted, {{before}} older).',
                { from: preview.period.from, to: preview.period.to, counted: preview.lines.counted,
                  deleted: preview.lines.deleted, before: preview.lines.before_period })}
              {' '}
              {Object.entries(preview.currencies).map(([c, v]) => formatSpend(v, c)).join(' · ')}
            </p>
          ) : <p className="text-gray-500">{t('spend.none', 'No order lines in the file can be counted.')}</p>}
          {preview.top.length > 0 && (
            <table className="min-w-full text-xs">
              <thead><tr className="text-left text-gray-500 uppercase">
                <th className="py-1">#</th><th className="py-1">{t('spend.supplier', 'Supplier')}</th>
                <th className="py-1">{t('spend.spend', 'Spend')}</th><th className="py-1">{t('spend.share', 'Share')}</th>
              </tr></thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                {preview.top.slice(0, 10).map((r) => (
                  <tr key={r.number}>
                    <td className="py-1 text-gray-500">{r.rank}</td>
                    <td className="py-1">{r.name} <span className="font-mono text-gray-400">{r.number}</span></td>
                    <td className="py-1">{preview.main_currency ? formatSpend(r.spend[preview.main_currency] ?? '0', preview.main_currency) : '–'}
                      {Object.keys(r.spend).filter((c) => c !== preview.main_currency).map((c) => ` + ${formatSpend(r.spend[c], c)}`).join('')}</td>
                    <td className="py-1">{r.share !== null ? `${(r.share * 100).toFixed(1)}%` : '–'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {preview.unknown_count > 0 && (
            <p className="text-xs text-amber-700">
              {t('spend.unknown', '{{count}} SAP supplier numbers have orders but are not imported suppliers; their spend is not stored. Import the supplier master to include them.', { count: preview.unknown_count })}
            </p>
          )}
          {preview.warnings.length > 0 && (
            <ul className="list-disc pl-5 text-xs text-gray-600">{preview.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>
          )}
          <button type="button" disabled={busy || stale || preview.suppliers === 0} onClick={() => run(true)}
            className="px-4 py-2 rounded-lg text-sm font-medium bg-green-600 text-white hover:bg-green-700 disabled:opacity-50">
            {t('spend.apply', 'Save spend for {{count}} suppliers', { count: preview.suppliers })}
          </button>
          {stale && <p className="text-xs text-amber-700">{t('sap.stale', 'You changed a choice. Update the preview before importing.')}</p>}
        </div>
      )}
      {done && <p className="text-sm mt-3">{t('spend.done', 'Spend saved for {{count}} suppliers.', { count: done.written })}</p>}
    </div>
  );
}
