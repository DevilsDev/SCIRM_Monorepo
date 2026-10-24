import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api, ApiKey, SCIM_BASE_URL } from '../services/api';
import { utcDate } from '../services/time';

function errorText(err: any, fallback: string): string {
  return err?.response?.data?.detail || fallback;
}

// SCIM 2.0: the identity provider creates, updates and deactivates accounts (admins).
export default function ScimSettings() {
  const { t } = useTranslation();
  const [tokens, setTokens] = useState<ApiKey[]>([]);
  const [created, setCreated] = useState('');
  const [error, setError] = useState('');

  const load = useCallback(() => api.listApiKeys().then((r) => setTokens(r.api_keys.filter((k) => k.scopes.includes('scim'))))
    .catch((err) => setError(errorText(err, t('scim.loadFailed', 'Could not load the SCIM tokens.')))), [t]);
  useEffect(() => { load(); }, [load]);

  const create = async () => {
    setError('');
    try {
      const { key } = await api.createApiKey('SCIM provisioning', 365, 'scim');
      setCreated(key);
      await load();
    } catch (err) {
      setError(errorText(err, t('scim.createFailed', 'Could not create the token.')));
    }
  };

  const revoke = async (k: ApiKey) => {
    setError('');
    try {
      await api.revokeApiKey(k.id);
      await load();
    } catch (err) {
      setError(errorText(err, t('scim.revokeFailed', 'Could not revoke the token.')));
    }
  };

  const active = tokens.filter((k) => !k.revoked_at);
  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
      <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-1">{t('scim.title', 'User provisioning (SCIM)')}</h2>
      <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
        {t('scim.hint', 'Your identity provider (Entra, Okta, ...) creates accounts, updates names, emails and roles, and deactivates people who leave. Accounts it creates sign in with single sign-on.')}
      </p>
      <p className="text-xs text-gray-600 dark:text-gray-300 mb-3">
        {t('scim.url', 'Tenant URL:')} <code className="font-mono bg-gray-100 dark:bg-gray-700 px-1 rounded select-all">{SCIM_BASE_URL}</code>
      </p>
      {error && <p className="text-sm text-red-600 mb-3">{error}</p>}
      {created && (
        <div className="border border-amber-300 bg-amber-50 rounded-lg p-3 mb-3 text-xs text-amber-900">
          <p className="font-medium">{t('scim.token', 'Secret token')}</p>
          <input readOnly value={created} onFocus={(e) => e.currentTarget.select()}
            className="w-full mt-2 px-2 py-1 border border-amber-300 rounded bg-white font-mono text-[11px]" />
          <p className="mt-2">{t('scim.once', 'Paste it into your identity provider now: it will not be shown again. It expires in a year.')}</p>
        </div>
      )}
      {active.length > 0 && (
        <ul className="text-sm divide-y divide-gray-100 dark:divide-gray-700 mb-3">
          {active.map((k) => (
            <li key={k.id} className="py-2 flex items-center justify-between">
              <span>
                <span className="font-mono text-xs">{k.prefix}…</span>
                <span className="text-xs text-gray-500"> · {k.last_used_at
                  ? t('scim.lastUsed', 'last used {{at}}', { at: utcDate(k.last_used_at).toLocaleString() })
                  : t('scim.unused', 'not used yet')}</span>
              </span>
              <button type="button" onClick={() => revoke(k)} className="text-xs text-red-600 hover:underline">{t('scim.revoke', 'Revoke')}</button>
            </li>
          ))}
        </ul>
      )}
      <button type="button" onClick={create} className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700">
        {active.length ? t('scim.another', 'Create another token') : t('scim.create', 'Create SCIM token')}
      </button>
    </div>
  );
}
