import { FormEvent, useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api, SsoSettings as Settings } from '../services/api';

function errorText(err: any, fallback: string): string {
  return err?.response?.data?.detail || fallback;
}

// Single sign-on with the organization's identity provider (OpenID Connect), for admins.
export default function SsoSettings() {
  const { t } = useTranslation();
  const [settings, setSettings] = useState<Settings | null>(null);
  const [issuer, setIssuer] = useState('');
  const [clientId, setClientId] = useState('');
  const [secret, setSecret] = useState('');
  const [enforce, setEnforce] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const apply = (s: Settings) => {
    setSettings(s);
    setIssuer(s.config?.issuer || '');
    setClientId(s.config?.client_id || '');
    setEnforce(Boolean(s.config?.enforce));
    setSecret('');
  };
  const load = useCallback(() => api.getSso().then(apply)
    .catch((err) => setError(errorText(err, t('sso.loadFailed', 'Could not load the single sign-on settings.')))), [t]);
  useEffect(() => { load(); }, [load]);

  const save = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    setNotice('');
    try {
      apply(await api.saveSso({ issuer: issuer.trim(), client_id: clientId.trim(), client_secret: secret || undefined, enforce }));
      setNotice(t('sso.saved', 'Saved. The identity provider answered and its settings match.'));
    } catch (err) {
      setError(errorText(err, t('sso.saveFailed', 'Could not save the settings.')));
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    setError('');
    try {
      await api.deleteSso();
      setNotice(t('sso.removed', 'Single sign-on is off. Members sign in with their passwords.'));
      await load();
    } catch (err) {
      setError(errorText(err, t('sso.removeFailed', 'Could not remove single sign-on.')));
    }
  };

  const field = 'block w-full mt-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm bg-white dark:bg-gray-800 dark:text-white';
  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
      <div className="flex items-center justify-between mb-1">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">{t('sso.title', 'Single sign-on')}</h2>
        {settings?.config && (
          <span className="inline-flex px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-800">
            {settings.config.enforce ? t('sso.onEnforced', 'On · required') : t('sso.on', 'On')}
          </span>
        )}
      </div>
      <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
        {t('sso.hint', 'Members sign in through your identity provider (OpenID Connect: Microsoft Entra, Okta, Google, Keycloak and others). Their accounts must already exist in SCIRM (invite them); the first sign-in links the account to the provider.')}
      </p>
      {settings && !settings.available && (
        <p className="text-sm text-amber-700 mb-3">{t('sso.unavailable', 'This deployment is missing PUBLIC_APP_URL or PUBLIC_API_URL, so single sign-on cannot be used yet.')}</p>
      )}
      {settings?.redirect_uri && (
        <p className="text-xs text-gray-600 dark:text-gray-300 mb-3">
          {t('sso.redirect', 'Register this redirect URI at your identity provider:')}{' '}
          <code className="font-mono bg-gray-100 dark:bg-gray-700 px-1 rounded select-all">{settings.redirect_uri}</code>
        </p>
      )}
      {error && <p className="text-sm text-red-600 mb-3">{error}</p>}
      {notice && <p className="text-sm text-green-600 mb-3">{notice}</p>}
      <form onSubmit={save} className="space-y-3">
        <label className="block text-xs text-gray-500">{t('sso.issuer', 'Issuer URL')}
          <input required value={issuer} onChange={(e) => setIssuer(e.target.value)} className={field}
            placeholder="https://login.microsoftonline.com/<tenant id>/v2.0" />
        </label>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <label className="block text-xs text-gray-500">{t('sso.clientId', 'Client ID')}
            <input required value={clientId} onChange={(e) => setClientId(e.target.value)} className={field} />
          </label>
          <label className="block text-xs text-gray-500">{t('sso.secret', 'Client secret')}
            <input type="password" autoComplete="off" value={secret} onChange={(e) => setSecret(e.target.value)} className={field}
              placeholder={settings?.config ? t('sso.keepSecret', 'Leave empty to keep the stored secret') : ''}
              required={!settings?.config} />
          </label>
        </div>
        <label className="flex items-start gap-2 text-sm text-gray-700 dark:text-gray-300">
          <input type="checkbox" className="mt-1" checked={enforce} onChange={(e) => setEnforce(e.target.checked)} />
          <span>
            {t('sso.enforce', 'Require single sign-on for members')}
            <span className="block text-xs text-gray-500">
              {t('sso.enforceHint', 'Members can no longer sign in, reset or change a password in SCIRM. Administrators keep their password (with two-step sign-in) as a way in if the identity provider is down.')}
            </span>
          </span>
        </label>
        <div className="flex items-center gap-3">
          <button type="submit" disabled={busy} className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50">
            {busy ? t('sso.checking', 'Checking...') : t('sso.save', 'Check and save')}
          </button>
          {settings?.config && (
            <button type="button" onClick={remove} className="text-sm text-red-600 hover:underline">{t('sso.remove', 'Turn off single sign-on')}</button>
          )}
        </div>
      </form>
    </div>
  );
}
