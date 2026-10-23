import { FormEvent, Fragment, useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api, AuditCategory, AuditEntry, AuditFilters } from '../services/api';
import { useAuth } from '../contexts/AuthContext';
import { utcDate } from '../services/time';

const NAMED: Record<string, string> = {
  'auth.login': 'Signed in',
  'auth.login_failed': 'Failed sign-in',
  'auth.sso_login': 'Signed in with single sign-on',
  'auth.sso_login_failed': 'Failed single sign-on',
  'auth.password_reset_requested': 'Asked for a password reset link',
  'auth.password_reset': 'Reset their password with a link',
  'sso.configured': 'Set up single sign-on',
  'sso.removed': 'Turned off single sign-on',
  'mfa.enabled': 'Turned on two-step sign-in',
  'mfa.disabled': 'Turned off two-step sign-in',
  'mfa.reset_by_admin': "Reset a teammate's two-step sign-in",
  'invitation.accepted': 'Accepted an invitation',
  'audit.exported': 'Exported the audit log',
  'api_key.created': 'Created an API key',
  'api_key.revoked': 'Revoked an API key',
  'api_key.refused': 'API key refused',
  'webhook.created': 'Added a webhook',
  'webhook.deleted': 'Deleted a webhook',
  'report.scheduled': 'Scheduled a report',
  'report.deleted': 'Deleted a scheduled report',
  'integrations.sap.save': 'Saved the SAP connection',
  'integrations.sap.test': 'Tested the SAP connection',
  'integrations.sap.delete': 'Removed the SAP connection',
  'suppliers.import.sap': 'Imported suppliers from SAP',
  'suppliers.import.sap_spend': 'Imported purchase-order spend from SAP',
};

const ROUTES: Record<string, string> = {
  'POST /api/v1/org/invitations': 'Invited a teammate',
  'DELETE /api/v1/org/invitations/{invitation_id}': 'Revoked an invitation',
  'PATCH /api/v1/org/members/{member_id}': "Changed a teammate's role or access",
  'POST /api/v1/org/api-keys': 'Created an API key',
  'DELETE /api/v1/org/api-keys/{key_id}': 'Revoked an API key',
  'POST /api/v1/org/webhooks': 'Added a webhook',
  'PATCH /api/v1/org/webhooks/{webhook_id}': 'Paused, resumed or changed a webhook',
  'DELETE /api/v1/org/webhooks/{webhook_id}': 'Deleted a webhook',
  'POST /api/v1/org/webhooks/{webhook_id}/test': 'Sent a test webhook',
  'POST /api/v1/org/reports': 'Scheduled a report',
  'PATCH /api/v1/org/reports/{schedule_id}': 'Paused, resumed or changed a scheduled report',
  'DELETE /api/v1/org/reports/{schedule_id}': 'Deleted a scheduled report',
  'POST /api/v1/org/reports/{schedule_id}/send-now': 'Sent a report now',
  'POST /api/v1/org/members/{member_id}/mfa/reset': "Reset a teammate's two-step sign-in",
  'POST /api/v1/auth/mfa/setup': 'Started two-step sign-in setup',
  'POST /api/v1/auth/mfa/confirm': 'Confirmed two-step sign-in',
  'POST /api/v1/auth/mfa/disable': 'Turned off two-step sign-in',
  'POST /api/v1/auth/change-password': 'Changed their password',
  'POST /api/v1/feedback': 'Rated a record or answer',
  'POST /api/v1/auth/reset-password': 'Reset their password',
  'POST /api/v1/auth/forgot-password': 'Asked for a password reset link',
  'PUT /api/v1/org/sso': 'Saved single sign-on settings',
  'DELETE /api/v1/org/sso': 'Turned off single sign-on',
  'POST /api/v1/suppliers': 'Added a supplier',
  'PUT /api/v1/suppliers/{supplier_id}': 'Edited a supplier',
  'DELETE /api/v1/suppliers/{supplier_id}': 'Deleted a supplier',
  'POST /api/v1/suppliers/{supplier_id}/ask': 'Asked about a supplier',
  'POST /api/v1/suppliers/{supplier_id}/sites': 'Added a supplier site',
  'DELETE /api/v1/suppliers/{supplier_id}/sites/{site_id}': 'Removed a supplier site',
  'POST /api/v1/suppliers/import/sap': 'Imported suppliers from an SAP file (or previewed)',
  'POST /api/v1/suppliers/import/sap/connection': 'Imported suppliers from SAP (or previewed)',
  'POST /api/v1/suppliers/import/sap-spend': 'Imported purchase-order spend from a file (or previewed)',
  'POST /api/v1/suppliers/import/sap-spend/connection': 'Imported purchase-order spend from SAP (or previewed)',
  'PUT /api/v1/integrations/sap': 'Saved the SAP connection',
  'DELETE /api/v1/integrations/sap': 'Removed the SAP connection',
  'POST /api/v1/integrations/sap/test': 'Tested the SAP connection',
  'POST /api/v1/scan': 'Ran a supplier scan',
  'POST /api/v1/risks': 'Added a risk',
  'PUT /api/v1/risks/{risk_id}': 'Edited a risk',
  'POST /api/v1/alerts/{alert_id}/acknowledge': 'Acknowledged an alert',
  'POST /api/v1/chat': 'Asked the assistant',
};

const VERBS: Record<string, string> = { POST: 'Created or ran', PUT: 'Updated', PATCH: 'Updated', DELETE: 'Deleted' };

/** A plain-language description of an audit action; the raw action is shown beside it. */
export function describeAction(action: string): string {
  if (NAMED[action]) return NAMED[action];
  if (ROUTES[action]) return ROUTES[action];
  const match = /^(POST|PUT|PATCH|DELETE) \/api\/v1\/([^/{]+)/.exec(action);
  return match ? `${VERBS[match[1]]} ${match[2].replace(/[-_]/g, ' ')}` : action;
}

/** Local calendar days -> the UTC instants the API filters on (until is exclusive). */
export function dayRange(from: string, to: string): { since?: string; until?: string } {
  const range: { since?: string; until?: string } = {};
  if (from) range.since = new Date(`${from}T00:00:00`).toISOString();
  if (to) {
    const end = new Date(`${to}T00:00:00`);
    end.setDate(end.getDate() + 1);
    range.until = end.toISOString();
  }
  return range;
}

const CATEGORIES: Array<{ value: AuditCategory | ''; label: string }> = [
  { value: '', label: 'All activity' },
  { value: 'sign_in', label: 'Sign-ins' },
  { value: 'access', label: 'Access and team' },
  { value: 'integrations', label: 'Integrations and imports' },
  { value: 'changes', label: 'Data changes' },
];

const input = 'px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm bg-white dark:bg-gray-800 dark:text-white';

// Who did what, when, from the organization's append-only audit log (admins and auditors).
export default function AuditLogPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const allowed = !!user?.roles?.some((r) => r === 'admin' || r === 'auditor');
  const [category, setCategory] = useState<AuditCategory | ''>('');
  const [actor, setActor] = useState('');
  const [failed, setFailed] = useState(false);
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [applied, setApplied] = useState<AuditFilters>({});
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const load = useCallback(async (filters: AuditFilters, before?: string) => {
    setLoading(true);
    setError('');
    try {
      const page = await api.listAudit({ ...filters, limit: 100, before });
      setEntries((current) => (before ? [...current, ...page.entries] : page.entries));
      setCursor(page.next_cursor);
    } catch {
      setError(t('audit.loadFailed', 'Could not load the audit log.'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => { if (allowed) load({}); }, [allowed, load]);

  const apply = (e: FormEvent) => {
    e.preventDefault();
    const filters: AuditFilters = { category, actor: actor.trim(), failed, ...dayRange(from, to) };
    setApplied(filters);
    setNotice('');
    load(filters);
  };

  const exportCsv = async () => {
    setError('');
    try {
      const { csv, rows, truncated } = await api.exportAudit(applied);
      const url = URL.createObjectURL(csv);
      const a = document.createElement('a');
      a.href = url;
      a.download = `scirm-audit-${new Date().toISOString().slice(0, 10)}.csv`;
      a.click();
      URL.revokeObjectURL(url);
      setNotice(truncated
        ? t('audit.exportTruncated', 'Exported the newest {{rows}} entries (the limit). Narrow the dates to export the rest.', { rows })
        : t('audit.exported', 'Exported {{rows}} entries.', { rows }));
    } catch {
      setError(t('audit.exportFailed', 'Could not export the audit log.'));
    }
  };

  if (!allowed) {
    return <p className="text-sm text-gray-500">{t('audit.forbidden', 'The audit log is available to administrators and auditors.')}</p>;
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{t('audit.title', 'Audit log')}</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            {t('audit.subtitle', 'Every sign-in and change in your organization. Entries cannot be edited or deleted.')}
          </p>
        </div>
        <button type="button" onClick={exportCsv}
          className="px-4 py-2 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg text-sm font-medium text-gray-700 dark:text-gray-200 hover:bg-gray-50">
          {t('audit.export', 'Export CSV')}
        </button>
      </div>

      <form onSubmit={apply} className="flex flex-wrap items-end gap-2 bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
        <label className="text-xs text-gray-500">{t('audit.category', 'Activity')}
          <select className={`${input} block mt-1`} value={category} onChange={(e) => setCategory(e.target.value as AuditCategory | '')}>
            {CATEGORIES.map((c) => <option key={c.value} value={c.value}>{t(`audit.cat.${c.value || 'all'}`, c.label)}</option>)}
          </select>
        </label>
        <label className="text-xs text-gray-500">{t('audit.actor', 'Person (email)')}
          <input className={`${input} block mt-1`} value={actor} onChange={(e) => setActor(e.target.value)} placeholder="name@company.com" />
        </label>
        <label className="text-xs text-gray-500">{t('audit.from', 'From')}
          <input type="date" className={`${input} block mt-1`} value={from} onChange={(e) => setFrom(e.target.value)} />
        </label>
        <label className="text-xs text-gray-500">{t('audit.to', 'To')}
          <input type="date" className={`${input} block mt-1`} value={to} onChange={(e) => setTo(e.target.value)} />
        </label>
        <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300 pb-2">
          <input type="checkbox" checked={failed} onChange={(e) => setFailed(e.target.checked)} />
          {t('audit.failedOnly', 'Failed or refused only')}
        </label>
        <button type="submit" className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700">
          {t('audit.apply', 'Apply')}
        </button>
      </form>

      {error && <p className="text-sm text-red-600">{error}</p>}
      {notice && <p className="text-sm text-green-600">{notice}</p>}

      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead className="bg-gray-50 dark:bg-gray-900">
            <tr className="text-left text-xs text-gray-500 dark:text-gray-400 uppercase">
              <th className="px-4 py-2">{t('audit.when', 'When')}</th>
              <th className="px-4 py-2">{t('audit.who', 'Who')}</th>
              <th className="px-4 py-2">{t('audit.what', 'What')}</th>
              <th className="px-4 py-2">{t('audit.result', 'Result')}</th>
              <th className="px-4 py-2">{t('audit.from', 'From')}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
            {entries.map((e) => {
              const bad = (e.status_code ?? 0) >= 400;
              return (
                <Fragment key={e.id}>
                  <tr className="cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700/40" onClick={() => setOpen(open === e.id ? null : e.id)}>
                    <td className="px-4 py-2 whitespace-nowrap text-gray-600 dark:text-gray-300">{utcDate(e.created_at).toLocaleString()}</td>
                    <td className="px-4 py-2 text-gray-900 dark:text-white">{e.actor || t('audit.anonymous', 'Not signed in')}</td>
                    <td className="px-4 py-2">
                      <span className="text-gray-900 dark:text-white">{describeAction(e.action)}</span>
                      <span className="block font-mono text-[11px] text-gray-400">{e.action}</span>
                    </td>
                    <td className="px-4 py-2">
                      {e.status_code != null && (
                        <span className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${bad ? 'bg-red-100 text-red-800' : 'bg-green-100 text-green-800'}`}>
                          {bad ? t('audit.refused', 'Refused') : t('audit.ok', 'OK')} · {e.status_code}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-2 font-mono text-xs text-gray-500">{e.ip_address || '–'}</td>
                  </tr>
                  {open === e.id && (
                    <tr className="bg-gray-50 dark:bg-gray-900/40">
                      <td colSpan={5} className="px-4 py-2">
                        <pre className="text-xs text-gray-700 dark:text-gray-300 whitespace-pre-wrap break-all">
                          {JSON.stringify({ resource: e.resource_type, resource_id: e.resource_id, ...e.details }, null, 2)}
                        </pre>
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
        {!loading && entries.length === 0 && (
          <p className="text-sm text-gray-500 p-4">{t('audit.empty', 'No entries match these filters.')}</p>
        )}
      </div>

      {cursor && (
        <button type="button" disabled={loading} onClick={() => load(applied, cursor)}
          className="px-4 py-2 text-sm text-blue-600 hover:underline disabled:opacity-50">
          {loading ? t('audit.loading', 'Loading...') : t('audit.more', 'Load older entries')}
        </button>
      )}
    </div>
  );
}
