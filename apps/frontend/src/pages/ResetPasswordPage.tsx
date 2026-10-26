import { FormEvent, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { api } from '../services/api';

// The link from the reset email: /reset-password#<token>. The token stays in the fragment,
// so it is never sent to a server in a URL or a Referer header.
export default function ResetPasswordPage() {
  const { t } = useTranslation();
  const [token] = useState(() => window.location.hash.slice(1));
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [done, setDone] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    if (password.length < 8) { setError(t('auth.passwordTooShort', 'Password must be at least 8 characters')); return; }
    if (password !== confirm) { setError(t('auth.passwordMismatch', 'Passwords do not match')); return; }
    setBusy(true);
    try {
      setDone((await api.resetPassword(token, password)).message);
      window.history.replaceState(null, '', window.location.pathname);  // drop the used token
    } catch (err: any) {
      setError(err?.response?.data?.detail || t('auth.resetFailed', 'The password could not be reset.'));
    } finally {
      setBusy(false);
    }
  };

  const field = 'w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg outline-none focus:ring-2 focus:ring-blue-500 text-gray-900 dark:text-white bg-white dark:bg-gray-800';
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-100 dark:bg-gray-900">
      <div className="w-full max-w-md bg-white dark:bg-gray-800 rounded-xl shadow-lg p-8">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white text-center mb-6">{t('auth.choosePassword', 'Choose a new password')}</h1>
        {done ? (
          <div className="text-center">
            <p className="text-sm text-gray-700 dark:text-gray-300">{done}</p>
            <Link to="/login" className="inline-block mt-4 text-sm text-blue-600 hover:text-blue-800 font-medium">{t('auth.backToSignIn', 'Back to Sign In')}</Link>
          </div>
        ) : !token ? (
          <p className="text-sm text-red-600 text-center">
            {t('auth.resetNoToken', 'This page needs the link from the reset email.')}{' '}
            <Link to="/forgot-password" className="text-blue-600">{t('auth.askNewLink', 'Ask for a new link')}</Link>
          </p>
        ) : (
          <form onSubmit={submit} className="space-y-4">
            <input type="password" autoComplete="new-password" required value={password} onChange={(e) => setPassword(e.target.value)}
              placeholder={t('auth.newPassword', 'New password')} className={field} />
            <input type="password" autoComplete="new-password" required value={confirm} onChange={(e) => setConfirm(e.target.value)}
              placeholder={t('auth.confirmPassword', 'Repeat the new password')} className={field} />
            {error && <p className="text-sm text-red-600">{error}</p>}
            <button type="submit" disabled={busy} className="w-full py-2.5 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50">
              {t('auth.setPassword', 'Set password')}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
