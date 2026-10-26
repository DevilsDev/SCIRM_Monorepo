import { FormEvent, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import QRCode from 'qrcode';
import { api } from '../services/api';

type Status = { enabled: boolean; pending: boolean; enforced_at_sign_in: boolean };

/** The key in groups of four, as authenticator apps show it. */
export function groupKey(secret: string): string {
  return secret.replace(/(.{4})/g, '$1 ').trim();
}

function apiError(err: unknown, fallback: string): string {
  return (err as any)?.response?.data?.detail || fallback;
}

// Two-step sign-in (TOTP). Setup stays pending until a code from the authenticator confirms
// it, so a mistyped key cannot lock anyone out. The QR code is drawn here in the browser:
// the key is never sent to a QR service.
export default function MfaSettings() {
  const { t } = useTranslation();
  const [status, setStatus] = useState<Status | null>(null);
  const [setup, setSetup] = useState<{ secret: string; qr: string } | null>(null);
  const [code, setCode] = useState('');
  const [disabling, setDisabling] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  const load = () => api.getMfaStatus().then(setStatus)
    .catch(() => setError(t('mfa.loadFailed', 'Could not load your two-step sign-in settings.')));
  useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const reset = () => { setCode(''); setError(''); setMessage(''); };

  const start = async () => {
    reset();
    setBusy(true);
    try {
      const { secret, otpauth_uri } = await api.setupMfa();
      setSetup({ secret, qr: await QRCode.toDataURL(otpauth_uri, { margin: 1, width: 180 }) });
    } catch (err) {
      setError(apiError(err, t('mfa.setupFailed', 'Could not start setup.')));
    } finally {
      setBusy(false);
    }
  };

  const confirm = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      await api.confirmMfa(code.replace(/\s/g, ''));
      setSetup(null);
      setCode('');
      setMessage(t('mfa.enabledNow', 'Two-step sign-in is on. You will be asked for a code when you sign in.'));
      await load();
    } catch (err) {
      setError(apiError(err, t('mfa.confirmFailed', 'That code did not work.')));
    } finally {
      setBusy(false);
    }
  };

  const disable = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      await api.disableMfa(code.replace(/\s/g, ''));
      setDisabling(false);
      setCode('');
      setMessage(t('mfa.disabledNow', 'Two-step sign-in is off.'));
      await load();
    } catch (err) {
      setError(apiError(err, t('mfa.disableFailed', 'That code did not work.')));
    } finally {
      setBusy(false);
    }
  };

  const codeInput = (
    <input
      value={code}
      onChange={(e) => setCode(e.target.value)}
      inputMode="numeric"
      autoComplete="one-time-code"
      maxLength={8}
      placeholder="123456"
      aria-label={t('mfa.code', 'Code from your authenticator app')}
      className="w-32 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white font-mono tracking-widest"
      required
    />
  );

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
      <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-1">{t('mfa.title', 'Two-step sign-in')}</h2>
      <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">
        {t('mfa.hint', 'After your password, sign-in asks for a 6-digit code from an authenticator app (Microsoft Authenticator, Google Authenticator, 1Password and others). If you lose your phone, an administrator can reset it.')}
      </p>
      {status && !status.enforced_at_sign_in && (
        <p className="text-xs text-amber-700 mb-3">
          {t('mfa.notEnforced', 'This deployment does not ask for codes at sign-in (MFA_ENABLED=false). You can set it up, but it has no effect until that changes.')}
        </p>
      )}
      {error && <p className="text-sm text-red-600 mb-3">{error}</p>}
      {message && <p className="text-sm text-green-600 mb-3">{message}</p>}

      {status?.enabled ? (
        disabling ? (
          <form onSubmit={disable} className="flex flex-wrap items-center gap-2">
            <span className="text-sm text-gray-700 dark:text-gray-300">{t('mfa.disablePrompt', 'Enter a current code to turn it off:')}</span>
            {codeInput}
            <button type="submit" disabled={busy} className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50">
              {t('mfa.disable', 'Turn off')}
            </button>
            <button type="button" onClick={() => { setDisabling(false); reset(); }} className="px-3 py-2 text-sm text-gray-600 dark:text-gray-300">
              {t('common.cancel', 'Cancel')}
            </button>
          </form>
        ) : (
          <div className="flex items-center gap-3">
            <span className="inline-flex px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-800">{t('mfa.on', 'On')}</span>
            <button type="button" onClick={() => { reset(); setDisabling(true); }} className="text-sm text-red-600 hover:underline">
              {t('mfa.turnOff', 'Turn off two-step sign-in')}
            </button>
          </div>
        )
      ) : setup ? (
        <div className="space-y-3">
          <ol className="text-sm text-gray-700 dark:text-gray-300 list-decimal ml-5 space-y-1">
            <li>{t('mfa.step1', 'In your authenticator app, add an account and scan this code, or type the key.')}</li>
            <li>{t('mfa.step2', 'Enter the 6-digit code the app shows.')}</li>
          </ol>
          <div className="flex flex-wrap items-center gap-4">
            <img src={setup.qr} alt={t('mfa.qrAlt', 'QR code for your authenticator app')} width={180} height={180} className="rounded bg-white p-1" />
            <div>
              <p className="text-xs text-gray-500 dark:text-gray-400">{t('mfa.key', 'Key')}</p>
              <p className="font-mono text-sm text-gray-900 dark:text-white select-all">{groupKey(setup.secret)}</p>
            </div>
          </div>
          <form onSubmit={confirm} className="flex flex-wrap items-center gap-2">
            {codeInput}
            <button type="submit" disabled={busy} className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50">
              {t('mfa.confirm', 'Confirm and turn on')}
            </button>
            <button type="button" onClick={() => { setSetup(null); reset(); }} className="px-3 py-2 text-sm text-gray-600 dark:text-gray-300">
              {t('common.cancel', 'Cancel')}
            </button>
          </form>
        </div>
      ) : status ? (
        <div className="flex items-center gap-3">
          <span className="inline-flex px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-700">{t('mfa.off', 'Off')}</span>
          <button type="button" onClick={start} disabled={busy} className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50">
            {t('mfa.setUp', 'Set up two-step sign-in')}
          </button>
        </div>
      ) : null}
    </div>
  );
}
