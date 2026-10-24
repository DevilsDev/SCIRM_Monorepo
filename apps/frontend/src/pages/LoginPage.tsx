import { useState, useRef } from 'react';
import { useNavigate, Link, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAuth } from '../contexts/AuthContext';
import { ssoStartUrl } from '../services/api';
import { newSsoBinding } from '../services/ssoBinding';

const MAX_ATTEMPTS = 5;

// Why single sign-on sent the person back here (the gateway's ?sso= reason).
const SSO_MESSAGES: Record<string, string> = {
  // Deliberately one answer for an unknown email, a deactivated account and an organization
  // without SSO, so the message does not reveal which accounts exist.
  unavailable: 'Single sign-on is not available for this email. Check the address, sign in with your password if you have one, or ask your administrator.',
  no_account: 'Your identity provider signed you in, but there is no active SCIRM account for you in that organization. Ask your administrator.',
  denied: 'The sign-in was cancelled or refused at your identity provider.',
  expired: 'The sign-in took too long or was started in another browser. Try again.',
  failed: 'Single sign-on failed. Try again, or ask your administrator to check the identity provider settings.',
  provider_error: 'Your identity provider could not be reached. Try again later.',
  account_ready: 'Your account is ready. Your organization signs in with single sign-on: enter your email and choose "Sign in with SSO".',
};
const LOCKOUT_SECONDS = 60;

export default function LoginPage() {
  const { login, verifyMfa } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const { t } = useTranslation();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [attempts, setAttempts] = useState(0);
  const [lockedUntil, setLockedUntil] = useState<number | null>(null);
  const lockTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Second step when MFA is on: the password step returns a short-lived token, not a session.
  const [mfaToken, setMfaToken] = useState<string | null>(null);
  const [code, setCode] = useState('');
  const expired = Boolean((location.state as any)?.expired);
  const ssoReason = new URLSearchParams(location.search).get('sso');

  // Where to redirect after login (saved by ProtectedRoute)
  const redirectTo = (location.state as any)?.from || '/dashboard';

  const isLocked = lockedUntil && Date.now() < lockedUntil;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isLocked) return;

    setError('');
    setLoading(true);

    try {
      if (mfaToken) {
        await verifyMfa(mfaToken, code.trim());
      } else {
        const result = await login(email, password);
        if (result.status === 'mfa_required') {
          setMfaToken(result.mfaToken);
          return;
        }
      }
      setAttempts(0);
      navigate(redirectTo, { replace: true });
    } catch (err: any) {
      const newAttempts = attempts + 1;
      setAttempts(newAttempts);

      if (newAttempts >= MAX_ATTEMPTS) {
        const until = Date.now() + LOCKOUT_SECONDS * 1000;
        setLockedUntil(until);
        setError(t('auth.tooManyAttempts', 'Too many failed attempts. Try again in {{seconds}} seconds.', { seconds: LOCKOUT_SECONDS }));
        lockTimer.current = setTimeout(() => {
          setLockedUntil(null);
          setAttempts(0);
          setError('');
        }, LOCKOUT_SECONDS * 1000);
      } else {
        setError(err.response?.data?.detail || t('auth.attemptsRemaining', 'Login failed. {{count}} attempt(s) remaining.', { count: MAX_ATTEMPTS - newAttempts }));
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-100 dark:bg-gray-700">
      <div className="w-full max-w-md">
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-lg p-8">
          <div className="text-center mb-8">
            <h1 className="text-3xl font-bold text-gray-900 dark:text-white">SCIRM</h1>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">Supply Chain Risk Management</p>
          </div>

          {ssoReason && SSO_MESSAGES[ssoReason] && !error && (
            <p className="text-sm text-amber-700 bg-amber-50 rounded-lg px-3 py-2 mb-4">
              {t(`auth.sso.${ssoReason}`, SSO_MESSAGES[ssoReason])}
            </p>
          )}

          {expired && !error && (
            <p className="text-sm text-amber-700 bg-amber-50 rounded-lg px-3 py-2 mb-4">
              {t('auth.sessionExpired', 'Your session has ended. Sign in again to return to where you were.')}
            </p>
          )}

          <form onSubmit={handleSubmit} className="space-y-5">
            {mfaToken ? (
            <div>
              <label htmlFor="totp" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                {t('auth.mfaCode', 'Authentication code')}
              </label>
              <input
                id="totp"
                inputMode="numeric"
                autoComplete="one-time-code"
                pattern="[0-9]{6}"
                maxLength={6}
                required
                autoFocus
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/[^0-9]/g, ''))}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none tracking-widest"
                placeholder="123456"
              />
              <p className="text-xs text-gray-400 mt-1">
                {t('auth.mfaHint', 'Enter the 6-digit code from your authenticator app.')}{' '}
                <button type="button" className="text-blue-600" onClick={() => { setMfaToken(null); setCode(''); setError(''); }}>
                  {t('auth.mfaBack', 'Use a different account')}
                </button>
              </p>
            </div>
            ) : (
            <>
            <div>
              <label htmlFor="email" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                {t('auth.email', 'Email')}
              </label>
              <input
                id="email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
                placeholder={t('auth.emailPlaceholder', 'you@company.com')}
              />
            </div>

            <div>
              <label htmlFor="password" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                {t('auth.password', 'Password')}
              </label>
              <input
                id="password"
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
                placeholder={t('auth.passwordPlaceholder', 'Enter your password')}
              />
            </div>
            </>
            )}

            {error && (
              <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {loading ? t('auth.signingIn', 'Signing in...') : mfaToken ? t('auth.verify', 'Verify') : t('auth.signIn', 'Sign in')}
            </button>
          </form>

          {!mfaToken && (
            <button
              type="button"
              onClick={async () => {
                if (!email.includes('@')) { setError(t('auth.ssoNeedsEmail', 'Enter your email first.')); return; }
                window.location.assign(ssoStartUrl(email.trim(), redirectTo, await newSsoBinding()));
              }}
              className="w-full mt-3 py-2.5 border border-gray-300 dark:border-gray-600 rounded-lg font-medium text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700"
            >
              {t('auth.ssoSignIn', 'Sign in with SSO')}
            </button>
          )}

          <div className="flex items-center justify-between mt-6">
            <Link to="/forgot-password" className="text-xs text-gray-400 hover:text-gray-600 dark:hover:text-gray-200">
              {t('auth.forgotPassword', 'Forgot password?')}
            </Link>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              <Link to="/signup" className="text-blue-600 hover:text-blue-800 font-medium">
                {t('auth.createAccount', 'Create account')}
              </Link>
            </p>
          </div>

          {import.meta.env.DEV && (
            <p className="text-xs text-gray-400 text-center mt-2">
              {t('auth.devCredentials', 'Dev mode: demo accounts use DEV_PASSWORD, or the password printed in the api-gateway log')}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
