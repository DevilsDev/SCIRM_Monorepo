import { FormEvent, useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAuth } from '../contexts/AuthContext';
import { api, InvitationPreview } from '../services/api';
import { clearInviteToken, inviteErrorMessage, readInviteToken } from '../services/invite';

export default function AcceptInvitePage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { user, acceptInvitation, logout } = useAuth();
  // Read once and take it out of the address bar straight away (see services/invite.ts).
  const tokenRef = useRef<string | null>(readInviteToken(window.location.hash));
  const [preview, setPreview] = useState<InvitationPreview | null>(null);
  const [loadError, setLoadError] = useState('');
  const [name, setName] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    const token = tokenRef.current;
    if (window.location.hash) clearInviteToken();
    if (!token) {
      setLoadError(t('invite.missing', 'This link is incomplete. Open the full invitation link you were sent.'));
      return;
    }
    api.lookupInvitation(token)
      .then(setPreview)
      .catch((err) => setLoadError(inviteErrorMessage(err?.response?.status)));
  }, [t]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    if (password.length < 8) return setError(t('invite.passwordShort', 'Use at least 8 characters.'));
    if (password !== confirm) return setError(t('invite.passwordMismatch', 'The passwords do not match.'));
    setSubmitting(true);
    try {
      if (user) logout(); // joining as the invited person, not whoever was signed in on this browser
      const result = await acceptInvitation(tokenRef.current!, name.trim(), password);
      navigate(result === 'sso_required' ? '/login?sso=account_ready' : '/dashboard', { replace: true });
    } catch (err: any) {
      setError(inviteErrorMessage(err?.response?.status));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-100 dark:bg-gray-700 p-4">
      <div className="w-full max-w-md bg-white dark:bg-gray-800 rounded-xl shadow-lg p-8">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white text-center">SCIRM</h1>
        {loadError ? (
          <div className="mt-6 space-y-4">
            <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{loadError}</p>
            <Link to="/login" className="block text-center text-sm text-blue-600">{t('invite.toLogin', 'Go to sign in')}</Link>
          </div>
        ) : !preview ? (
          <p className="text-sm text-gray-400 text-center mt-6">{t('invite.checking', 'Checking your invitation...')}</p>
        ) : (
          <>
            <p className="text-sm text-gray-600 dark:text-gray-300 text-center mt-2">
              {t('invite.joining', 'You have been invited to join {{org}} as {{roles}}.', {
                org: preview.organization_name, roles: preview.roles.join(', '),
              })}
            </p>
            {user && (
              <p className="text-xs text-amber-700 bg-amber-50 rounded-lg px-3 py-2 mt-4">
                {t('invite.signedInAs', 'You are signed in as {{email}}. Accepting signs you out and creates the invited account.', { email: user.email })}
              </p>
            )}
            <form onSubmit={submit} className="space-y-4 mt-6">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{t('invite.email', 'Email')}</label>
                <p className="text-sm text-gray-900 dark:text-white">{preview.email}</p>
              </div>
              <div>
                <label htmlFor="invite-name" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{t('invite.name', 'Your name')}</label>
                <input id="invite-name" required maxLength={255} value={name} onChange={(e) => setName(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg outline-none focus:ring-2 focus:ring-blue-500" />
              </div>
              <div>
                <label htmlFor="invite-password" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{t('invite.password', 'Choose a password')}</label>
                <input id="invite-password" type="password" required autoComplete="new-password" value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg outline-none focus:ring-2 focus:ring-blue-500" />
              </div>
              <div>
                <label htmlFor="invite-confirm" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{t('invite.confirm', 'Repeat the password')}</label>
                <input id="invite-confirm" type="password" required autoComplete="new-password" value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg outline-none focus:ring-2 focus:ring-blue-500" />
              </div>
              {error && <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>}
              <button type="submit" disabled={submitting}
                className="w-full py-2.5 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50">
                {submitting ? t('invite.joiningButton', 'Joining...') : t('invite.accept', 'Join {{org}}', { org: preview.organization_name })}
              </button>
              <p className="text-[11px] text-gray-400 text-center">
                {t('invite.expires', 'This invitation expires on {{date}}.', { date: new Date(preview.expires_at).toLocaleString() })}
              </p>
            </form>
          </>
        )}
      </div>
    </div>
  );
}
