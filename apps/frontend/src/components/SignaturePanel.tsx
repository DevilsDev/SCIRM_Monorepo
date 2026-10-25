import { FormEvent, useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api, ESignature, SignableRecord, SignatureMeaning } from '../services/api';
import { utcDate } from '../services/time';

const input = 'px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm bg-white dark:bg-gray-800 dark:text-white';

export const MEANING_LABEL: Record<SignatureMeaning, string> = {
  reviewed: 'Reviewed', approved: 'Approved', responsible: 'Responsible',
};

/** The human-readable signature (21 CFR 11.50): printed name, date and time, meaning. */
export function signatureLine(s: Pick<ESignature, 'signer_name' | 'signer_email' | 'meaning' | 'signed_at'>): string {
  return `${MEANING_LABEL[s.meaning]} by ${s.signer_name} (${s.signer_email}), ${utcDate(s.signed_at).toLocaleString()}`;
}

/** The outcome of signing at the identity provider, from the URL fragment it returns with. */
export function ssoOutcome(hash: string): string | null {
  const m = /(?:^#|&)signature=([a-z_]+)/.exec(hash);
  return m ? m[1] : null;
}

const SSO_MESSAGES: Record<string, string> = {
  signed: 'Signed at your identity provider.',
  no_fresh_login: 'Not signed: your identity provider did not ask you to log in again. Try again.',
  different_person: 'Not signed: you logged in at your identity provider as someone else.',
  record_changed: 'Not signed: the record changed while you were signing. Review it and sign again.',
  failed: 'Not signed: the sign-in at your identity provider did not complete.',
};

function errorText(err: any, fallback: string): string {
  const detail = err?.response?.data?.detail;
  return typeof detail === 'string' ? detail : fallback;
}

// Electronic signatures on one record: who signed, when and with what meaning, and whether
// the record is still as signed. Signing re-authenticates every time: the password (and the
// two-step code), or a fresh login at the identity provider for SSO accounts.
export default function SignaturePanel({ recordType, recordId, meanings = ['reviewed', 'approved'] }: {
  recordType: SignableRecord; recordId: string; meanings?: SignatureMeaning[];
}) {
  const { t } = useTranslation();
  const [signatures, setSignatures] = useState<ESignature[]>([]);
  const [method, setMethod] = useState<'password' | 'password_mfa' | 'sso' | null>(null);
  const [open, setOpen] = useState(false);
  const [meaning, setMeaning] = useState<SignatureMeaning>(meanings[0]);
  const [reason, setReason] = useState('');
  const [password, setPassword] = useState('');
  const [code, setCode] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  const load = useCallback(() => api.listSignatures(recordType, recordId).then(setSignatures).catch(() => setSignatures([])), [recordType, recordId]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    const outcome = ssoOutcome(window.location.hash);
    if (outcome) {
      setMessage(SSO_MESSAGES[outcome] || SSO_MESSAGES.failed);
      window.history.replaceState(null, '', window.location.pathname + window.location.search);
    }
  }, []);

  const start = async () => {
    setOpen(true); setError(''); setMessage('');
    try { setMethod((await api.signatureMethod()).method); } catch (err) { setError(errorText(err, t('sig.failed', 'Signing is not available.'))); }
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    try {
      if (method === 'sso') {
        const next = window.location.pathname + window.location.search;
        window.location.href = await api.prepareSsoSignature({ record_type: recordType, record_id: recordId, meaning, reason, next });
        return;
      }
      await api.signWithPassword({ record_type: recordType, record_id: recordId, meaning, reason, password,
        ...(method === 'password_mfa' ? { totp_code: code } : {}) });
      setPassword(''); setCode(''); setReason(''); setOpen(false);
      setMessage(t('sig.done', 'Signed.'));
      load();
    } catch (err) { setError(errorText(err, t('sig.failed', 'The record could not be signed.'))); }
  };

  return (
    <div className="mt-4 border-t border-gray-100 dark:border-gray-700 pt-3">
      <h3 className="text-sm font-semibold text-gray-900 dark:text-white">{t('sig.title', 'Electronic signatures')}</h3>
      {signatures.length === 0 && <p className="text-xs text-gray-500 mt-1">{t('sig.none', 'Not signed.')}</p>}
      <ul className="mt-1 space-y-1">
        {signatures.map((s) => (
          <li key={s.id} className="text-sm text-gray-800 dark:text-gray-200">
            ✍ {signatureLine(s)}
            {s.reason && <span className="text-gray-500"> · {s.reason}</span>}
            {s.intact === false && <span className="ml-2 text-xs text-red-600">{t('sig.changed', 'record changed after signing')}</span>}
          </li>
        ))}
      </ul>
      {message && <p className="mt-1 text-sm text-green-700 dark:text-green-400">{message}</p>}
      {!open ? (
        <button type="button" onClick={start} className="mt-2 text-sm text-blue-600 hover:underline">{t('sig.sign', 'Sign')}</button>
      ) : (
        <form onSubmit={submit} className="mt-2 space-y-2">
          <div className="flex flex-wrap gap-2">
            <select value={meaning} onChange={(e) => setMeaning(e.target.value as SignatureMeaning)} className={input} aria-label={t('sig.meaning', 'Meaning')}>
              {meanings.map((m) => <option key={m} value={m}>{MEANING_LABEL[m]}</option>)}
            </select>
            <input value={reason} onChange={(e) => setReason(e.target.value)} maxLength={1000} placeholder={t('sig.reason', 'Comment (optional)')} className={`${input} flex-1 min-w-[160px]`} />
          </div>
          {method && method !== 'sso' && (
            <div className="flex flex-wrap gap-2">
              <input type="password" required autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)}
                placeholder={t('sig.password', 'Your password')} className={input} aria-label={t('sig.password', 'Your password')} />
              {method === 'password_mfa' && (
                <input inputMode="numeric" required value={code} onChange={(e) => setCode(e.target.value)} maxLength={10}
                  placeholder={t('sig.code', 'Two-step code')} className={`${input} w-32`} aria-label={t('sig.code', 'Two-step code')} />
              )}
            </div>
          )}
          <p className="text-xs text-gray-500">
            {method === 'sso'
              ? t('sig.ssoHint', 'You will log in again at your identity provider; the signature is recorded when you come back.')
              : t('sig.hint', 'Signing is the equivalent of your handwritten signature: it records your name, the date and time, and the meaning.')}
          </p>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <div className="flex gap-2">
            <button type="submit" disabled={!method} className="px-3 py-1.5 rounded-lg text-sm font-medium bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50">
              {method === 'sso' ? t('sig.signSso', 'Sign at my identity provider') : t('sig.signNow', 'Sign')}
            </button>
            <button type="button" onClick={() => setOpen(false)} className="px-3 py-1.5 rounded-lg text-sm text-gray-600 dark:text-gray-300">{t('common.cancel', 'Cancel')}</button>
          </div>
        </form>
      )}
    </div>
  );
}
