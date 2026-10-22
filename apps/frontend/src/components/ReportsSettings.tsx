import { FormEvent, useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api, ReportFrequency, ReportSchedule } from '../services/api';
import { utcDate } from '../services/time';

const WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

/** "07:00 UTC (09:00 your time)" for an hour in UTC. */
export function hourLabel(hourUtc: number, now: Date = new Date()): string {
  const d = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate(), hourUtc));
  const local = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  return `${String(hourUtc).padStart(2, '0')}:00 UTC (${local} your time)`;
}

function errorText(err: any, fallback: string): string {
  return err?.response?.data?.detail || fallback;
}

// A supplier risk digest emailed to members on a schedule (admins).
export default function ReportsSettings() {
  const { t } = useTranslation();
  const [schedules, setSchedules] = useState<ReportSchedule[]>([]);
  const [members, setMembers] = useState<string[]>([]);
  const [emailOn, setEmailOn] = useState(true);
  const [name, setName] = useState('Weekly supplier digest');
  const [frequency, setFrequency] = useState<ReportFrequency>('weekly');
  const [weekday, setWeekday] = useState(0);
  const [hour, setHour] = useState(7);
  const [recipients, setRecipients] = useState<string[]>([]);
  const [skipEmpty, setSkipEmpty] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');

  const load = useCallback(() => api.listReports().then((r) => {
    setSchedules(r.schedules);
    setMembers(r.members);
    setEmailOn(r.email_configured);
  }).catch((err) => setError(errorText(err, t('reports.loadFailed', 'Could not load the scheduled reports.')))), [t]);
  useEffect(() => { load(); }, [load]);

  const create = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    setNotice('');
    try {
      await api.createReport({ name: name.trim(), frequency, hour_utc: hour, weekday: frequency === 'weekly' ? weekday : null,
        recipients, skip_empty: skipEmpty });
      setRecipients([]);
      await load();
    } catch (err) {
      setError(errorText(err, t('reports.createFailed', 'Could not schedule the report.')));
    }
  };

  const act = async (s: ReportSchedule, action: 'send' | 'toggle' | 'delete') => {
    setError('');
    setNotice('');
    try {
      if (action === 'send') {
        await api.sendReportNow(s.id);
        setNotice(t('reports.queued', '"{{name}}" is queued and will be sent within about a minute.', { name: s.name }));
      } else if (action === 'toggle') {
        await api.updateReport(s.id, { active: !s.active });
      } else {
        await api.deleteReport(s.id);
      }
      await load();
    } catch (err) {
      setError(errorText(err, t('reports.actionFailed', 'That did not work.')));
    }
  };

  const toggleRecipient = (email: string) =>
    setRecipients((current) => (current.includes(email) ? current.filter((r) => r !== email) : [...current, email]));

  const field = 'px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm bg-white dark:bg-gray-800 dark:text-white';
  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
      <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-1">{t('reports.title', 'Scheduled reports')}</h2>
      <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
        {t('reports.hint', 'A supplier risk digest by email: new public records naming your suppliers and new disaster exposures since the last report. Only members of your organization can receive it.')}
      </p>
      {!emailOn && (
        <p className="text-sm text-amber-700 mb-3">
          {t('reports.noEmail', 'Email is not configured on this deployment (SMTP), so reports cannot be sent yet. You can still set them up.')}
        </p>
      )}
      {error && <p className="text-sm text-red-600 mb-3">{error}</p>}
      {notice && <p className="text-sm text-green-600 mb-3">{notice}</p>}

      <form onSubmit={create} className="space-y-3 mb-4">
        <div className="flex flex-wrap items-end gap-2">
          <label className="text-xs text-gray-500">{t('reports.name', 'Name')}
            <input required maxLength={100} value={name} onChange={(e) => setName(e.target.value)} className={`${field} block mt-1 w-56`} />
          </label>
          <label className="text-xs text-gray-500">{t('reports.frequency', 'How often')}
            <select value={frequency} onChange={(e) => setFrequency(e.target.value as ReportFrequency)} className={`${field} block mt-1`}>
              <option value="daily">{t('reports.daily', 'Daily')}</option>
              <option value="weekly">{t('reports.weekly', 'Weekly')}</option>
              <option value="monthly">{t('reports.monthly', 'Monthly (on the 1st)')}</option>
            </select>
          </label>
          {frequency === 'weekly' && (
            <label className="text-xs text-gray-500">{t('reports.day', 'Day')}
              <select value={weekday} onChange={(e) => setWeekday(Number(e.target.value))} className={`${field} block mt-1`}>
                {WEEKDAYS.map((d, i) => <option key={d} value={i}>{d}</option>)}
              </select>
            </label>
          )}
          <label className="text-xs text-gray-500">{t('reports.time', 'Time')}
            <select value={hour} onChange={(e) => setHour(Number(e.target.value))} className={`${field} block mt-1`}>
              {Array.from({ length: 24 }, (_, h) => <option key={h} value={h}>{hourLabel(h)}</option>)}
            </select>
          </label>
        </div>
        <div>
          <p className="text-xs text-gray-500 mb-1">{t('reports.recipients', 'Send to')}</p>
          <div className="flex flex-wrap gap-x-4 gap-y-1">
            {members.map((m) => (
              <label key={m} className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
                <input type="checkbox" checked={recipients.includes(m)} onChange={() => toggleRecipient(m)} />{m}
              </label>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-4">
          <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
            <input type="checkbox" checked={skipEmpty} onChange={(e) => setSkipEmpty(e.target.checked)} />
            {t('reports.skipEmpty', "Don't send when there is nothing new")}
          </label>
          <button type="submit" disabled={recipients.length === 0}
            className="ml-auto px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50">
            {t('reports.schedule', 'Schedule report')}
          </button>
        </div>
      </form>

      {schedules.length > 0 && (
        <table className="min-w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-gray-500 dark:text-gray-400 uppercase">
              <th className="py-2">{t('reports.report', 'Report')}</th>
              <th className="py-2">{t('reports.next', 'Next')}</th>
              <th className="py-2">{t('reports.last', 'Last')}</th>
              <th className="py-2" />
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
            {schedules.map((s) => (
              <tr key={s.id} className={s.active ? '' : 'opacity-60'}>
                <td className="py-2">
                  <p className="font-medium text-gray-900 dark:text-white">{s.name}</p>
                  <p className="text-xs text-gray-500">{s.when} · {s.recipients.join(', ')}{!s.active && ` · ${t('reports.paused', 'paused')}`}</p>
                </td>
                <td className="py-2 text-xs text-gray-500">{s.active ? utcDate(s.next_run_at).toLocaleString() : '–'}</td>
                <td className="py-2 text-xs">
                  {s.last_status ? (
                    <span className={s.last_status.ok ? 'text-green-700' : 'text-red-600'}>
                      {s.last_status.ok
                        ? (s.last_status.sent ? t('reports.sent', 'Sent ({{n}} items)', { n: s.last_status.events ?? 0 }) : t('reports.notNeeded', 'Nothing new, not sent'))
                        : s.last_status.error}
                      <span className="block text-gray-500">{utcDate(s.last_status.at).toLocaleString()}</span>
                    </span>
                  ) : <span className="text-gray-400">{t('reports.never', 'not yet')}</span>}
                </td>
                <td className="py-2 text-right whitespace-nowrap space-x-3 text-xs">
                  <button type="button" disabled={!emailOn} className="text-blue-600 hover:underline disabled:opacity-40" onClick={() => act(s, 'send')}>
                    {t('reports.sendNow', 'Send now')}
                  </button>
                  <button type="button" className="text-blue-600 hover:underline" onClick={() => act(s, 'toggle')}>
                    {s.active ? t('reports.pause', 'Pause') : t('reports.resume', 'Resume')}
                  </button>
                  <button type="button" className="text-red-600 hover:underline" onClick={() => act(s, 'delete')}>{t('reports.delete', 'Delete')}</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
