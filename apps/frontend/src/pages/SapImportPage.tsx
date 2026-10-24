import { ChangeEvent, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { api, SapConnection, SapImportResult } from '../services/api';
import { decodeExport, headerCells } from '../services/fileText';
import SapSpendImport from '../components/SapSpendImport';
import SapConnectionPanel from '../components/SapConnectionPanel';

const MAX_BYTES = 20_000_000;
const MAPPABLE: Array<{ field: string; column: string; label: string }> = [
  { field: 'number', column: 'LIFNR', label: 'Supplier number' },
  { field: 'name1', column: 'NAME1', label: 'Name' },
  { field: 'name2', column: 'NAME2', label: 'Name 2' },
  { field: 'country', column: 'LAND1', label: 'Country' },
  { field: 'posting_block', column: 'SPERR', label: 'Posting block' },
  { field: 'purchasing_block', column: 'SPERM', label: 'Purchasing block' },
  { field: 'deletion_flag', column: 'LOEVM', label: 'Deletion flag' },
];
const ACTION_LABELS: Record<string, string> = {
  create: 'New', update: 'Updated', link: 'Linked to an existing supplier', unchanged: 'Unchanged',
  deactivate: 'Deactivated', skip: 'Skipped', needs_decision: 'Needs your decision',
};

export default function SapImportPage() {
  const { t } = useTranslation();
  const [content, setContent] = useState('');
  const [fileName, setFileName] = useState('');
  const [headers, setHeaders] = useState<string[]>([]);
  const [columnMap, setColumnMap] = useState<Record<string, string>>({});
  const [decisions, setDecisions] = useState<Record<string, string>>({});
  const [deactivateMissing, setDeactivateMissing] = useState(false);
  const [preview, setPreview] = useState<SapImportResult | null>(null);
  const [stale, setStale] = useState(false);
  const [done, setDone] = useState<SapImportResult | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [connection, setConnection] = useState<SapConnection | null>(null);
  // Where the supplier master comes from: an uploaded LFA1 file, or the SAP connection.
  const [source, setSource] = useState<'file' | 'connection'>('file');

  useEffect(() => {
    api.getSapConnection().then((c) => {
      setConnection(c);
      if (c) setSource('connection');
    }).catch(() => setConnection(null));
  }, []);

  const pickSource = (next: 'file' | 'connection') => {
    setSource(next);
    setPreview(null);
    setDone(null);
    setDecisions({});
    setError('');
  };

  const technical = headers.some((h) => h.toUpperCase() === 'LIFNR');

  const onFile = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setPreview(null);
    setDone(null);
    setError('');
    if (file.size > MAX_BYTES) {
      setError(t('sap.tooBig', 'The file is larger than 20 MB.'));
      return;
    }
    const text = decodeExport(new Uint8Array(await file.arrayBuffer()));
    setFileName(file.name);
    setContent(text);
    setHeaders(headerCells(text));
    setColumnMap({});
    setDecisions({});
  };

  const run = async (apply: boolean) => {
    setBusy(true);
    setError('');
    try {
      const mapped = Object.fromEntries(Object.entries(columnMap).filter(([, v]) => v));
      const result = source === 'connection'
        ? await api.importSapSuppliersFromConnection({ decisions, deactivate_missing: deactivateMissing, apply })
        : await api.importSapSuppliers({ content, column_map: mapped, decisions, deactivate_missing: deactivateMissing, apply });
      if (apply) {
        setDone(result);
        setPreview(null);
      } else {
        setPreview(result);
        setStale(false);
      }
    } catch (err: any) {
      setError(err?.response?.data?.detail || t('sap.failed', 'The import failed. Try again in a moment.'));
    } finally {
      setBusy(false);
    }
  };

  const change = (update: () => void) => {
    update();
    if (preview) setStale(true);
  };

  const card = 'bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6';
  const button = 'px-4 py-2 rounded-lg text-sm font-medium disabled:opacity-50';
  const writes = preview ? (preview.summary.create || 0) + (preview.summary.update || 0) + (preview.summary.link || 0)
    + (preview.summary.deactivate || 0) : 0;

  return (
    <div className="space-y-6 max-w-5xl">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{t('sap.title', 'Import suppliers from SAP')}</h1>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
          {t('sap.intro2', 'Read the supplier master from your SAP S/4HANA system, or upload an export of table LFA1 (for example from transaction SE16N). You see what will change before anything is saved.')}
        </p>
      </div>

      <SapConnectionPanel connection={connection} onChange={(c) => { setConnection(c); if (!c) pickSource('file'); }} />

      {connection && (
        <div className="flex gap-2 text-sm" role="radiogroup" aria-label={t('sap.source', 'Import from')}>
          {(['connection', 'file'] as const).map((s) => (
            <button key={s} type="button" role="radio" aria-checked={source === s} onClick={() => pickSource(s)}
              className={`px-3 py-1.5 rounded-lg border ${source === s ? 'bg-blue-600 text-white border-blue-600' : 'border-gray-300 dark:border-gray-600'}`}>
              {s === 'connection' ? t('sap.fromConnection', 'From the SAP connection') : t('sap.fromFile', 'From a file')}
            </button>
          ))}
        </div>
      )}

      {source === 'connection' && connection && (
        <div className={card}>
          <p className="text-sm text-gray-600 dark:text-gray-300">
            {t('sap.connectionHint', 'Reads every supplier from {{url}}. Importing reads SAP again, so the result can differ slightly from the preview if suppliers changed in between.', { url: connection.base_url })}
          </p>
          <div className="flex gap-2 mt-4">
            <button type="button" disabled={busy} onClick={() => run(false)}
              className={`${button} bg-blue-600 text-white hover:bg-blue-700`}>
              {busy ? t('sap.reading', 'Reading from SAP...') : preview ? t('sap.updatePreview', 'Update preview') : t('sap.previewFromSap', 'Preview from SAP')}
            </button>
          </div>
          {error && <p className="text-sm text-red-600 mt-3">{error}</p>}
        </div>
      )}

      {source === 'file' && <div className={card}>
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
          {t('sap.file', 'LFA1 export (tab-, semicolon- or comma-separated text)')}
        </label>
        <input type="file" accept=".txt,.csv,.tsv,text/plain,text/csv" onChange={onFile} className="text-sm" />
        <p className="text-xs text-gray-500 mt-2">
          {t('sap.columns', 'Columns used: LIFNR and NAME1 (required), NAME2 to NAME4, LAND1, ORT01, SPERR, SPERM, LOEVM, STCEG.')}
        </p>
        {fileName && headers.length > 0 && !technical && (
          <div className="mt-4 border border-amber-300 bg-amber-50 rounded-lg p-3">
            <p className="text-xs text-amber-900 mb-2">
              {t('sap.mapHint', 'This file has column labels instead of SAP field names. Choose which column holds each field.')}
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {MAPPABLE.map((m) => (
                <label key={m.field} className="text-xs text-gray-700 flex items-center gap-2">
                  <span className="w-40">{m.label} ({m.column})</span>
                  <select value={columnMap[m.field] || ''} className="flex-1 px-2 py-1 border rounded text-xs bg-white"
                    onChange={(e) => change(() => setColumnMap({ ...columnMap, [m.field]: e.target.value }))}>
                    <option value="">{t('sap.notInFile', '(not in file)')}</option>
                    {headers.map((h) => <option key={h} value={h}>{h}</option>)}
                  </select>
                </label>
              ))}
            </div>
          </div>
        )}
        <div className="flex gap-2 mt-4">
          <button type="button" disabled={!content || busy} onClick={() => run(false)}
            className={`${button} bg-blue-600 text-white hover:bg-blue-700`}>
            {busy ? t('sap.working', 'Working...') : preview ? t('sap.updatePreview', 'Update preview') : t('sap.preview', 'Preview')}
          </button>
        </div>
        {error && <p className="text-sm text-red-600 mt-3">{error}</p>}
      </div>}

      {preview && (
        <div className={card}>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">
            {t('sap.previewTitle', 'What the import will do')} ({source === 'connection' ? t('sap.rowsSap', '{{count}} suppliers in SAP', { count: preview.rows }) : t('sap.rows', '{{count}} suppliers in the file', { count: preview.rows })})
          </h2>
          <div className="flex flex-wrap gap-2 mb-4">
            {Object.entries(preview.summary).map(([action, count]) => (
              <span key={action} className="px-2 py-1 rounded-full bg-gray-100 dark:bg-gray-700 text-xs">
                {ACTION_LABELS[action] || action}: <strong>{count}</strong>
              </span>
            ))}
          </div>

          {preview.duplicates.length > 0 && (
            <section className="mb-4">
              <h3 className="text-sm font-semibold mb-1">{t('sap.duplicates', 'Same name as a supplier entered by hand')}</h3>
              <p className="text-xs text-gray-500 mb-2">
                {t('sap.duplicatesHint', 'Nothing is created or merged for these until you choose. Linking keeps the existing supplier and its history, and adds the SAP number to it.')}
              </p>
              <ul className="divide-y divide-gray-100 dark:divide-gray-700 text-sm">
                {preview.duplicates.map((d) => (
                  <li key={d.number} className="py-2 flex flex-wrap items-center gap-2 justify-between">
                    <span>{d.name} <span className="text-xs text-gray-500">SAP {d.number}{d.country_code && ` · ${d.country_code}`}</span></span>
                    <select className="px-2 py-1 border rounded text-xs bg-white dark:bg-gray-800"
                      value={decisions[d.number] || ''}
                      onChange={(e) => change(() => setDecisions({ ...decisions, [d.number]: e.target.value }))}>
                      <option value="">{t('sap.decideLater', 'Decide later (skip for now)')}</option>
                      <option value={`link:${d.existing_id}`}>{t('sap.link', 'Same supplier as {{name}} ({{code}})', { name: d.existing_name, code: d.existing_code })}</option>
                      <option value="create">{t('sap.create', 'A different supplier: create it')}</option>
                    </select>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {preview.missing.length > 0 && (
            <section className="mb-4">
              <label className="flex items-start gap-2 text-sm">
                <input type="checkbox" className="mt-1" checked={deactivateMissing}
                  onChange={(e) => change(() => setDeactivateMissing(e.target.checked))} />
                <span>
                  {t('sap.missing2', '{{count}} suppliers imported before are not in SAP any more (or not in this file). Deactivate them (nothing is deleted).', { count: preview.missing.length })}
                  <span className="block text-xs text-gray-500">{preview.missing.slice(0, 5).map((m) => m.name).join(', ')}{preview.missing.length > 5 && ', ...'}</span>
                </span>
              </label>
              {preview.guard && <p className="text-xs text-amber-700 mt-1">{preview.guard}</p>}
            </section>
          )}

          {preview.warnings.length > 0 && (
            <details className="mb-4 text-xs text-gray-600">
              <summary className="cursor-pointer">{t('sap.warnings', '{{count}} rows with problems', { count: preview.warnings.length })}</summary>
              <ul className="list-disc pl-5 mt-1">{preview.warnings.slice(0, 200).map((w, i) => <li key={i}>{w}</li>)}</ul>
            </details>
          )}

          {preview.actions.length > 0 && (
            <details className="mb-4 text-xs">
              <summary className="cursor-pointer text-gray-600">{t('sap.details', 'Changes by supplier')}</summary>
              <table className="min-w-full mt-2">
                <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                  {preview.actions.slice(0, 500).map((a) => (
                    <tr key={`${a.action}-${a.number}`}>
                      <td className="py-1 pr-2 font-mono text-gray-500">{a.number}</td>
                      <td className="py-1 pr-2">{a.name}</td>
                      <td className="py-1 pr-2">{ACTION_LABELS[a.action] || a.action}</td>
                      <td className="py-1 text-gray-500">{a.reason || (a.changed?.length ? a.changed.join(', ') : '')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </details>
          )}

          <button type="button" disabled={busy || stale || writes === 0} onClick={() => run(true)}
            className={`${button} bg-green-600 text-white hover:bg-green-700`}>
            {t('sap.apply', 'Import: save {{count}} changes', { count: writes })}
          </button>
          {stale && <p className="text-xs text-amber-700 mt-2">{t('sap.stale', 'You changed a choice. Update the preview before importing.')}</p>}
        </div>
      )}

      {done && (
        <div className={card}>
          <p className="text-sm text-gray-900 dark:text-white">
            {t('sap.done', 'Imported: {{count}} suppliers saved.', { count: done.written })}{' '}
            <Link to="/suppliers" className="text-blue-600 hover:underline">{t('sap.toSuppliers', 'Go to suppliers')}</Link>
          </p>
          {done.duplicates.length > 0 && (
            <p className="text-xs text-gray-500 mt-1">
              {t('sap.leftOver2', '{{count}} possible duplicates were skipped; import again to decide on them.', { count: done.duplicates.length })}
            </p>
          )}
        </div>
      )}

      <SapSpendImport connected={!!connection} />
    </div>
  );
}
