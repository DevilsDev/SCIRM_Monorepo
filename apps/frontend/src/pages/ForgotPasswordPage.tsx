import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { api } from '../services/api';

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [sent, setSent] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const { t } = useTranslation();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setBusy(true);
    try {
      setSent((await api.forgotPassword(email.trim())).message);
    } catch (err: any) {
      setError(err?.response?.data?.detail || t('auth.resetFailed', 'The request could not be sent. Try again.'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-100 dark:bg-gray-900">
      <div className="w-full max-w-md">
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-lg p-8">
          <div className="text-center mb-6">
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{t('auth.resetPassword', 'Reset Password')}</h1>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">{t('auth.resetDescription', 'Enter your email to receive a reset link')}</p>
          </div>

          {sent ? (
            <div className="text-center">
              <div className="w-16 h-16 bg-green-100 dark:bg-green-900/30 rounded-full flex items-center justify-center mx-auto mb-4">
                <svg className="w-8 h-8 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" /></svg>
              </div>
              <p className="text-sm text-gray-700 dark:text-gray-300">{sent}</p>
              <Link to="/login" className="inline-block mt-4 text-sm text-blue-600 hover:text-blue-800 font-medium">{t('auth.backToSignIn', 'Back to Sign In')}</Link>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label htmlFor="email" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{t('auth.email', 'Email')}</label>
                <input
                  id="email" type="email" required value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none text-gray-900 dark:text-white bg-white dark:bg-gray-800"
                  placeholder={t('auth.emailPlaceholder', 'you@company.com')}
                />
              </div>
              {error && <p className="text-sm text-red-600">{error}</p>}
              <button type="submit" disabled={busy} className="w-full py-2.5 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50">
                {t('auth.sendResetLink', 'Send Reset Link')}
              </button>
              <p className="text-sm text-gray-500 dark:text-gray-400 text-center">
                <Link to="/login" className="text-blue-600 hover:text-blue-800 font-medium">{t('auth.backToSignIn', 'Back to Sign In')}</Link>
              </p>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
