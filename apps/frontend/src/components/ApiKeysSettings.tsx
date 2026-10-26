import { FormEvent, useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api, ApiKey } from '../services/api';
import { utcDate } from '../services/time';

const EXPIRY: Array<{ days: number | null; label: string }> = [
  { days: 90, label: '90 days' }, { days: 365, label: '1 year' }, { days: 30, label: '30 days' }, { days: null, label: 'Never' },
];

function status(k: ApiKey, t: (key: string, fallback: string) => string): { text: string; tone: string } {
  if (k.revoked_at) return { text: t('apiKeys.revoked', 'Revoked'), tone: 'bg-gray-100 text-gray-600' };
  if (k.expires_at && utcDate(k.expires_at) <= new Date()) return { text: t('apiKeys.expired', 'Expired'), tone: 'bg-gray-100 text-gray-600' };
  return { text: t('apiKeys.active', 'Active'), tone: 'bg-green-100 text-green-800' };
}

function errorText(err: any, fallback: string): string {
  return err?.response?.data?.detail || fallback;
}

// Read-only keys for the public API (admins). A key is shown once, when it is created.
export default function ApiKeysSettings() {
  const { t } = useTranslation();
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [name, setName] = useState('');
  const [days, setDays] = useState<number | null>(90);
  const [created, setCreated] = useState<{ name: string; key: string } | null>(null);
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(() => api.listApiKeys().then((r) => setKeys(r.api_keys.filter((k) => k.scopes.includes('read'))))
    .catch((err) => setError(errorText(err, t('apiKeys.loadFailed', 'Could not load the API keys.')))), [t]);
  useEffect(() => { load(); }, [load]);

  const create = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      const { key } = await api.createApiKey(name.trim(), days ?? undefined);
      setCreated({ name: name.trim(), key });
      setCopied(false);
      setName('');
      await load();
    } catch (err) {
      setError(errorText(err, t('apiKeys.createFailed', 'Could not create the key.')));
    } finally {
      setBusy(false);
    }
  };

  const revoke = async (k: ApiKey) => {
    setError('');
    try {
      await api.revokeApiKey(k.id);
      await load();
    } catch (err) {
      setError(errorText(err, t('apiKeys.revokeFailed', 'Could not revoke the key.')));
    }
  };

  const copy = async () => {
    if (!created) return;
    try {
      await navigator.clipboard.writeText(created.key);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
      <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-1">{t('apiKeys.title', 'API keys')}</h2>
      <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">
        {t('apiKeys.hint', 'Read-only access for other systems: suppliers, their public records, alerts, risks and the intelligence feed. Keys cannot change anything, see the team or read the audit log.')}
      </p>
      {error && <p className="text-sm text-red-600 mb-3">{error}</p>}

      <form onSubmit={create} className="flex flex-wrap items-end gap-2 mb-4">
        <label className="text-xs text-gray-500 flex-1 min-w-[200px]">{t('apiKeys.name', 'Name')}
          <input required maxLength={100} value={name} onChange={(e) => setName(e.target.value)} placeholder="Power BI refresh"
            className="block w-full mt-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm bg-white dark:bg-gray-800 dark:text-white" />
        </label>
        <label className="text-xs text-gray-500">{t('apiKeys.expires', 'Expires after')}
          <select value={days ?? ''} onChange={(e) => setDays(e.target.value ? Number(e.target.value) : null)}
            className="block mt-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm bg-white dark:bg-gray-800 dark:text-white">
            {EXPIRY.map((o) => <option key={o.label} value={o.days ?? ''}>{o.label}</option>)}
          </select>
        </label>
        <button type="submit" disabled={busy} className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50">
          {t('apiKeys.create', 'Create key')}
        </button>
      </form>

      {created && (
        <div className="border border-amber-300 bg-amber-50 rounded-lg p-3 mb-4 text-xs text-amber-900">
          <p className="font-medium">{t('apiKeys.createdFor', 'Key for {{name}}', { name: created.name })}</p>
          <div className="flex gap-2 mt-2">
            <input readOnly value={created.key} onFocus={(e) => e.currentTarget.select()}
              className="flex-1 px-2 py-1 border border-amber-300 rounded bg-white font-mono text-[11px]" />
            <button type="button" onClick={copy} className="px-2 py-1 bg-amber-600 text-white rounded">
              {copied ? t('apiKeys.copied', 'Copied') : t('apiKeys.copy', 'Copy')}
            </button>
          </div>
          <p className="mt-2">{t('apiKeys.once', 'Copy it now: it will not be shown again. Send it as "Authorization: Bearer <key>".')}</p>
        </div>
      )}

      {keys.length > 0 && (
        <table className="min-w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-gray-500 dark:text-gray-400 uppercase">
              <th className="py-2">{t('apiKeys.key', 'Key')}</th>
              <th className="py-2">{t('apiKeys.created', 'Created')}</th>
              <th className="py-2">{t('apiKeys.lastUsed', 'Last used')}</th>
              <th className="py-2">{t('apiKeys.status', 'Status')}</th>
              <th className="py-2" />
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
            {keys.map((k) => {
              const s = status(k, t);
              return (
                <tr key={k.id}>
                  <td className="py-2">
                    <p className="font-medium text-gray-900 dark:text-white">{k.name}</p>
                    <p className="font-mono text-xs text-gray-500">{k.prefix}…</p>
                  </td>
                  <td className="py-2 text-xs text-gray-500">
                    {utcDate(k.created_at).toLocaleDateString()}{k.created_by && ` · ${k.created_by}`}
                    {k.expires_at && !k.revoked_at && <span className="block">{t('apiKeys.until', 'until {{date}}', { date: utcDate(k.expires_at).toLocaleDateString() })}</span>}
                  </td>
                  <td className="py-2 text-xs text-gray-500">{k.last_used_at ? utcDate(k.last_used_at).toLocaleString() : t('apiKeys.never', 'never')}</td>
                  <td className="py-2"><span className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${s.tone}`}>{s.text}</span></td>
                  <td className="py-2 text-right">
                    {!k.revoked_at && (
                      <button type="button" onClick={() => revoke(k)} className="text-xs text-red-600 hover:underline">
                        {t('apiKeys.revoke', 'Revoke')}
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}
