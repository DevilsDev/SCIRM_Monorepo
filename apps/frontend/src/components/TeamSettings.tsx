import { FormEvent, useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '../contexts/AuthContext';
import { api, Invitation, Role, ROLES, TeamMember } from '../services/api';

const ROLE_HELP: Record<Role, string> = {
  admin: 'manages the team and settings',
  analyst: 'creates and edits assessments, suppliers and risks',
  viewer: 'read-only',
  auditor: 'read-only, plus the audit log',
};

function errorText(err: any, fallback: string): string {
  return err?.response?.data?.detail || fallback;
}

export default function TeamSettings() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const isAdmin = !!user?.roles?.includes('admin');
  const [members, setMembers] = useState<TeamMember[]>([]);
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [error, setError] = useState('');
  const [email, setEmail] = useState('');
  const [role, setRole] = useState<Role>('analyst');
  const [link, setLink] = useState<{ email: string; url: string } | null>(null);
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setMembers((await api.listMembers()).members);
      if (isAdmin) setInvitations((await api.listInvitations()).invitations);
    } catch (err) {
      setError(errorText(err, t('team.loadFailed', 'Could not load the team.')));
    }
  }, [isAdmin, t]);

  useEffect(() => { load(); }, [load]);

  const invite = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    setBusy(true);
    try {
      const result = await api.createInvitation(email.trim(), [role]);
      setLink({ email: result.invitation.email, url: result.invite_url });
      setCopied(false);
      setEmail('');
      await load();
    } catch (err) {
      setError(errorText(err, t('team.inviteFailed', 'Could not create the invitation.')));
    } finally {
      setBusy(false);
    }
  };

  const change = async (member: TeamMember, changes: { roles?: Role[]; is_active?: boolean }) => {
    setError('');
    try {
      await api.updateMember(member.id, changes);
      await load();
    } catch (err) {
      setError(errorText(err, t('team.updateFailed', 'Could not update this member.')));
    }
  };

  const revoke = async (invitation: Invitation) => {
    setError('');
    try {
      await api.revokeInvitation(invitation.id);
      await load();
    } catch (err) {
      setError(errorText(err, t('team.revokeFailed', 'Could not revoke this invitation.')));
    }
  };

  const copy = async () => {
    if (!link) return;
    try {
      await navigator.clipboard.writeText(link.url);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };

  const card = 'bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6';
  const select = 'px-2 py-1 border border-gray-300 dark:border-gray-600 rounded-lg text-xs bg-white dark:bg-gray-800';

  return (
    <div className={card}>
      <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-1">{t('team.title', 'Team')}</h2>
      <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">
        {isAdmin
          ? t('team.adminHint', 'Invite colleagues, change their roles, or deactivate accounts. Deactivation takes effect within an hour.')
          : t('team.memberHint', 'People in your organization. Ask an administrator to invite someone or change a role.')}
      </p>

      {error && <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2 mb-3">{error}</p>}

      {isAdmin && (
        <form onSubmit={invite} className="flex flex-wrap gap-2 items-end mb-4">
          <div className="flex-1 min-w-[200px]">
            <label htmlFor="invite-email" className="block text-xs text-gray-500 dark:text-gray-400 mb-1">{t('team.email', 'Email')}</label>
            <input id="invite-email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
              placeholder="colleague@company.com"
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm bg-white dark:bg-gray-800" />
          </div>
          <div>
            <label htmlFor="invite-role" className="block text-xs text-gray-500 dark:text-gray-400 mb-1">{t('team.role', 'Role')}</label>
            <select id="invite-role" value={role} onChange={(e) => setRole(e.target.value as Role)}
              className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm bg-white dark:bg-gray-800">
              {ROLES.map((r) => <option key={r} value={r}>{r}: {ROLE_HELP[r]}</option>)}
            </select>
          </div>
          <button type="submit" disabled={busy}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50">
            {busy ? t('team.inviting', 'Inviting...') : t('team.invite', 'Invite')}
          </button>
        </form>
      )}

      {link && (
        <div className="border border-amber-300 bg-amber-50 rounded-lg p-3 mb-4 text-xs text-amber-900">
          <p className="font-medium">{t('team.linkFor', 'Invitation link for {{email}}', { email: link.email })}</p>
          <div className="flex gap-2 mt-2">
            <input readOnly value={link.url} onFocus={(e) => e.currentTarget.select()}
              className="flex-1 px-2 py-1 border border-amber-300 rounded bg-white font-mono text-[11px]" />
            <button type="button" onClick={copy} className="px-2 py-1 bg-amber-600 text-white rounded">
              {copied ? t('team.copied', 'Copied') : t('team.copy', 'Copy')}
            </button>
          </div>
          <p className="mt-2">
            {t('team.linkWarning', 'Send it to this person only. It works once, expires in 7 days, and will not be shown again.')}
          </p>
        </div>
      )}

      <table className="min-w-full text-sm">
        <thead>
          <tr className="text-left text-xs text-gray-500 dark:text-gray-400 uppercase">
            <th className="py-2">{t('team.member', 'Member')}</th>
            <th className="py-2">{t('team.role', 'Role')}</th>
            <th className="py-2">{t('team.lastSignIn', 'Last sign-in')}</th>
            <th className="py-2" />
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
          {members.map((m) => (
            <tr key={m.id} className={m.is_active ? '' : 'opacity-50'}>
              <td className="py-2">
                <p className="font-medium text-gray-900 dark:text-white">{m.name}{m.id === user?.id && ` (${t('team.you', 'you')})`}</p>
                <p className="text-xs text-gray-500">{m.email}{!m.is_active && ` · ${t('team.deactivated', 'deactivated')}`}
                  {m.demo && ` · ${t('team.demo', 'demo account')}`}</p>
              </td>
              <td className="py-2">
                {isAdmin && !m.demo ? (
                  <select className={select} value={m.roles[0] || 'viewer'} aria-label={t('team.roleFor', 'Role for {{name}}', { name: m.name })}
                    onChange={(e) => change(m, { roles: [e.target.value as Role] })}>
                    {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
                  </select>
                ) : (
                  <span className="text-xs capitalize">{m.roles.join(', ')}</span>
                )}
              </td>
              <td className="py-2 text-xs text-gray-500">{m.last_login_at ? new Date(m.last_login_at).toLocaleString() : t('team.never', 'never')}</td>
              <td className="py-2 text-right">
                {isAdmin && !m.demo && m.id !== user?.id && (
                  <button type="button" className="text-xs text-blue-600 hover:underline"
                    onClick={() => change(m, { is_active: !m.is_active })}>
                    {m.is_active ? t('team.deactivate', 'Deactivate') : t('team.reactivate', 'Reactivate')}
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {isAdmin && invitations.length > 0 && (
        <>
          <h3 className="text-sm font-semibold text-gray-900 dark:text-white mt-6 mb-2">{t('team.invitations', 'Invitations')}</h3>
          <ul className="divide-y divide-gray-100 dark:divide-gray-700 text-sm">
            {invitations.map((i) => (
              <li key={i.id} className="py-2 flex items-center justify-between gap-2">
                <span>
                  {i.email} <span className="text-xs text-gray-500">· {i.roles.join(', ')} · {i.status}
                  {i.status === 'pending' && ` · ${t('team.expiresOn', 'expires {{date}}', { date: new Date(i.expires_at).toLocaleDateString() })}`}</span>
                </span>
                {i.status === 'pending' && (
                  <button type="button" className="text-xs text-red-600 hover:underline" onClick={() => revoke(i)}>
                    {t('team.revoke', 'Revoke')}
                  </button>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
