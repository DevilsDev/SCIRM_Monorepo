import { useState, useRef, DragEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { ArrowUpTrayIcon, DocumentTextIcon, XMarkIcon, CheckCircleIcon } from '@heroicons/react/24/outline';

interface CSVUploadProps {
  onUpload: (rows: Record<string, string>[]) => Promise<void>;
  expectedColumns: string[];
  entityLabel: string; // 'suppliers' | 'components'
}

export default function CSVUpload({ onUpload, expectedColumns, entityLabel }: CSVUploadProps) {
  const { t } = useTranslation();
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<Record<string, string>[]>([]);
  const [errors, setErrors] = useState<string[]>([]);
  const [uploading, setUploading] = useState(false);
  const [success, setSuccess] = useState(false);
  const [dragOver, setDragOver] = useState(false);

  const parseCSV = (text: string): Record<string, string>[] => {
    const lines = text.trim().split('\n');
    if (lines.length < 2) return [];
    const headers = lines[0].split(',').map((h) => h.trim().replace(/^"|"$/g, ''));
    return lines.slice(1).map((line) => {
      const vals = line.split(',').map((v) => v.trim().replace(/^"|"$/g, ''));
      const row: Record<string, string> = {};
      headers.forEach((h, i) => { row[h] = vals[i] || ''; });
      return row;
    });
  };

  const handleFile = (f: File) => {
    setFile(f);
    setErrors([]);
    setSuccess(false);

    const reader = new FileReader();
    reader.onload = (e) => {
      const text = e.target?.result as string;
      const rows = parseCSV(text);

      // Validate columns
      if (rows.length > 0) {
        const cols = Object.keys(rows[0]);
        const missing = expectedColumns.filter((c) => !cols.includes(c));
        if (missing.length > 0) {
          setErrors([t('csv.missingColumns', 'Missing required columns: {{cols}}', { cols: missing.join(', ') })]);
          setPreview([]);
          return;
        }
      }

      setPreview(rows.slice(0, 5)); // Show first 5 rows as preview
    };
    reader.readAsText(f);
  };

  const handleDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files[0];
    if (f && (f.name.endsWith('.csv') || f.name.endsWith('.tsv'))) {
      handleFile(f);
    } else {
      setErrors([t('csv.invalidFile', 'Please upload a CSV file')]);
    }
  };

  const handleSubmit = async () => {
    if (!file) return;
    setUploading(true);
    try {
      const text = await file.text();
      const rows = parseCSV(text);
      await onUpload(rows);
      setSuccess(true);
      setFile(null);
      setPreview([]);
    } catch (err: any) {
      setErrors([err.message || t('csv.uploadFailed', 'Upload failed')]);
    } finally {
      setUploading(false);
    }
  };

  if (success) {
    return (
      <div className="text-center py-8">
        <CheckCircleIcon className="h-12 w-12 text-green-500 mx-auto mb-3" />
        <p className="text-sm font-medium text-gray-900 dark:text-white">{t('csv.success', 'Import successful!')}</p>
        <button
          onClick={() => { setSuccess(false); setFile(null); setPreview([]); }}
          className="mt-3 text-sm text-blue-600 hover:text-blue-800"
        >
          {t('csv.uploadAnother', 'Upload another file')}
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Drop zone */}
      {!file && (
        <div
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
          onClick={() => fileRef.current?.click()}
          className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors ${
            dragOver
              ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20'
              : 'border-gray-300 dark:border-gray-600 hover:border-blue-400 hover:bg-gray-50 dark:hover:bg-gray-700/50'
          }`}
        >
          <ArrowUpTrayIcon className="h-10 w-10 text-gray-400 mx-auto mb-3" />
          <p className="text-sm font-medium text-gray-900 dark:text-white">{t('csv.dropHere', 'Drop CSV file here or click to browse')}</p>
          <p className="text-xs text-gray-400 mt-1">{t('csv.expectedColumns', 'Expected columns: {{cols}}', { cols: expectedColumns.join(', ') })}</p>
          <input
            ref={fileRef}
            type="file"
            accept=".csv,.tsv"
            className="hidden"
            onChange={(e) => { if (e.target.files?.[0]) handleFile(e.target.files[0]); }}
          />
        </div>
      )}

      {/* File selected */}
      {file && (
        <div className="flex items-center gap-3 p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg border border-blue-200 dark:border-blue-800">
          <DocumentTextIcon className="h-8 w-8 text-blue-500" />
          <div className="flex-1">
            <p className="text-sm font-medium text-gray-900 dark:text-white">{file.name}</p>
            <p className="text-xs text-gray-500">{(file.size / 1024).toFixed(1)} KB — {preview.length > 0 ? `${preview.length}+ rows` : 'parsing...'}</p>
          </div>
          <button onClick={() => { setFile(null); setPreview([]); setErrors([]); }} className="p-1 hover:bg-blue-100 rounded">
            <XMarkIcon className="h-4 w-4 text-gray-500" />
          </button>
        </div>
      )}

      {/* Preview table */}
      {preview.length > 0 && (
        <div className="overflow-x-auto">
          <p className="text-xs text-gray-500 mb-2">{t('csv.preview', 'Preview (first 5 rows):')}</p>
          <table className="min-w-full text-xs border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
            <thead className="bg-gray-50 dark:bg-gray-900">
              <tr>
                {Object.keys(preview[0]).map((col) => (
                  <th key={col} className="px-3 py-2 text-left font-medium text-gray-500 dark:text-gray-400">{col}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
              {preview.map((row, i) => (
                <tr key={i}>
                  {Object.values(row).map((val, j) => (
                    <td key={j} className="px-3 py-2 text-gray-700 dark:text-gray-300">{val}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Errors */}
      {errors.length > 0 && (
        <div className="p-3 bg-red-50 dark:bg-red-900/20 rounded-lg border border-red-200 dark:border-red-800">
          {errors.map((err, i) => (
            <p key={i} className="text-xs text-red-600">{err}</p>
          ))}
        </div>
      )}

      {/* Submit */}
      {file && preview.length > 0 && errors.length === 0 && (
        <button
          onClick={handleSubmit}
          disabled={uploading}
          className="w-full px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors disabled:opacity-50"
        >
          {uploading ? t('common.loading', 'Loading...') : t('csv.import', 'Import {{count}} {{entity}}', { count: preview.length + '+', entity: entityLabel })}
        </button>
      )}
    </div>
  );
}
