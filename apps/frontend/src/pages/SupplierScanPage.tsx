import { ChangeEvent, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api, ScanResult } from '../services/api';

const EXAMPLE = 'name;country;aliases\nAcme Pharmaceuticals Inc.;US;Acme Pharma\nExample API Manufacturer Ltd;India;\n';

export default function SupplierScanPage() {
  const { t } = useTranslation();
  const [csv, setCsv] = useState('');
  const [fileName, setFileName] = useState('');
  const [preparedFor, setPreparedFor] = useState('');
  const [result, setResult] = useState<ScanResult | null>(null);
  const [error, setError] = useState('');
  const [running, setRunning] = useState(false);

  const onFile = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 1_000_000) {
      setError(t('scan.tooBig', 'The file is larger than 1 MB. Split it into smaller lists.'));
      return;
    }
    setFileName(file.name);
    setCsv(await file.text());
    setError('');
  };

  const run = async () => {
    setRunning(true);
    setError('');
    setResult(null);
    try {
      setResult(await api.scanSuppliers(csv, preparedFor));
    } catch (err: any) {
      setError(err?.response?.data?.detail || t('scan.failed', 'The scan failed. Try again in a moment.'));
    } finally {
      setRunning(false);
    }
  };

  const download = () => {
    if (!result) return;
    const url = URL.createObjectURL(new Blob([result.html], { type: 'text/html' }));
    const a = document.createElement('a');
    a.href = url;
    a.download = `supplier-scan-${new Date().toISOString().slice(0, 10)}.html`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const s = result?.report.summary;
  return (
    <div className="space-y-6 max-w-5xl">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{t('scan.title', 'Supplier scan')}</h1>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
          {t('scan.subtitle', 'Check a list of suppliers against public FDA records: recalls, warning letters, import alerts and shortages. The list is not stored.')}
        </p>
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6 space-y-4">
        <div className="flex flex-wrap gap-4 items-end">
          <label className="text-sm">
            <span className="block text-xs text-gray-500 mb-1">{t('scan.file', 'Supplier list (CSV)')}</span>
            <input type="file" accept=".csv,text/csv,text/plain" onChange={onFile} className="text-sm" />
          </label>
          <label className="text-sm flex-1 min-w-[200px]">
            <span className="block text-xs text-gray-500 mb-1">{t('scan.preparedFor', 'Prepared for (optional)')}</span>
            <input value={preparedFor} maxLength={200} onChange={(e) => setPreparedFor(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm bg-white dark:bg-gray-800" />
          </label>
          <button type="button" onClick={run} disabled={!csv.trim() || running}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50">
            {running ? t('scan.running', 'Scanning...') : t('scan.run', 'Run scan')}
          </button>
        </div>
        <details className="text-xs text-gray-500">
          <summary className="cursor-pointer">{t('scan.formatHelp', 'File format, or paste a list instead')}</summary>
          <p className="mt-2">
            {t('scan.format', 'A header row with a name column (name, supplier or company). Optional: country (code or name) and aliases (separated by ;). Comma or semicolon separated, as Excel exports it. Up to 500 suppliers.')}
          </p>
          <textarea rows={6} value={csv} placeholder={EXAMPLE}
            onChange={(e) => { setCsv(e.target.value); setFileName(''); }}
            className="w-full mt-2 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg font-mono text-xs bg-white dark:bg-gray-800" />
        </details>
        {fileName && <p className="text-xs text-gray-500">{t('scan.loaded', 'Loaded {{name}}', { name: fileName })}</p>}
        {error && <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>}
      </div>

      {result && s && (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-gray-700 dark:text-gray-300">
              {t('scan.summary', '{{scanned}} suppliers scanned: {{withRecords}} with public records, {{watch}} on Watch, {{check}} similar-name matches to check.', {
                scanned: s.scanned, withRecords: s.with_records, watch: s.watch, check: s.to_check,
              })}
            </p>
            <button type="button" onClick={download}
              className="px-3 py-1.5 bg-gray-200 dark:bg-gray-700 text-gray-800 dark:text-gray-200 rounded-lg text-sm">
              {t('scan.download', 'Download report')}
            </button>
          </div>
          {result.warnings.length > 0 && (
            <ul className="text-xs text-amber-700 bg-amber-50 rounded-lg px-4 py-2 list-disc">
              {result.warnings.map((w, i) => <li key={i}>{w}</li>)}
            </ul>
          )}
          {/* The report is self-contained HTML with no scripts; sandboxed all the same. */}
          <iframe title={t('scan.reportTitle', 'Supplier scan report')} sandbox="allow-popups allow-popups-to-escape-sandbox"
            srcDoc={result.html} className="w-full h-[70vh] bg-white rounded-xl border border-gray-200" />
        </div>
      )}
    </div>
  );
}
