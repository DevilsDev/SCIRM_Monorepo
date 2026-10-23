import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAuth } from '../contexts/AuthContext';
import { takeSsoBinding } from '../services/ssoBinding';

/** The one-time code and destination from /sso/complete#code=...&next=... */
export function readHandoff(hash: string): { code: string; next: string } {
  const params = new URLSearchParams(hash.replace(/^#/, ''));
  const next = params.get('next') || '/dashboard';
  // Only paths in this app (the gateway checks this too).
  const safe = next.startsWith('/') && !next.startsWith('//') && !next.includes('\\') ? next : '/dashboard';
  return { code: params.get('code') || '', next: safe };
}

// Where the identity provider's sign-in lands: trade the one-time code for a session. The
// code is in the fragment, so it never reaches a server log or a Referer header.
export default function SsoCompletePage() {
  const { t } = useTranslation();
  const { completeSso } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState('');
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;  // the code works once; React may run effects twice in development
    started.current = true;
    const { code, next } = readHandoff(window.location.hash);
    const binding = takeSsoBinding();
    window.history.replaceState(null, '', window.location.pathname);
    if (!code || !binding) {
      // No binding: the sign-in was not started from this tab's login page.
      setError(t('auth.ssoNoCode', 'Start single sign-on from the SCIRM sign-in page in this browser tab.'));
      return;
    }
    completeSso(code, binding)
      .then(() => navigate(next, { replace: true }))
      .catch((err) => setError(err?.response?.data?.detail || t('auth.ssoExchangeFailed', 'Sign-in failed. Try again.')));
  }, [completeSso, navigate, t]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-100 dark:bg-gray-900">
      <div className="w-full max-w-md bg-white dark:bg-gray-800 rounded-xl shadow-lg p-8 text-center">
        {error ? (
          <>
            <p className="text-sm text-red-600">{error}</p>
            <Link to="/login" className="inline-block mt-4 text-sm text-blue-600">{t('auth.backToSignIn', 'Back to Sign In')}</Link>
          </>
        ) : (
          <p className="text-sm text-gray-600 dark:text-gray-300">{t('auth.ssoSigningIn', 'Signing you in...')}</p>
        )}
      </div>
    </div>
  );
}
