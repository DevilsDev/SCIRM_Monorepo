import { FormEvent, Fragment, useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api, Webhook, WebhookDelivery, WebhookEvent } from '../services/api';
import { utcDate } from '../services/time';

const EVENTS: Array<{ value: WebhookEvent; label: string; hint: string }> = [
  { value: 'record.matched', label: 'New public record names a supplier', hint: 'FDA recall, shortage, warning letter or import alert' },
  { value: 'exposure.detected', label: 'New disaster near a supplier', hint: 'GDACS alert near a site, or in its country' },
];

function errorText(err: any, fallback: string): string {
  return err?.response?.data?.detail || fallback;
}

// Endpoints that receive signed events when new public records match the organization's
// suppliers (admins). The signing secret is shown once, when the endpoint is added.
export default function WebhooksSettings() {
  const { t } = useTranslation();
  const [hooks, setHooks] = useState<Webhook[]>([]);
  const [url, setUrl] = useState('');
  const [description, setDescription] = useState('');
  const [events, setEvents] = useState<WebhookEvent[]>(['record.matched', 'exposure.detected']);
  const [created, setCreated] = useState<{ url: string; secret: string } | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [deliveries, setDeliveries] = useState<WebhookDelivery[]>([]);
  const [notice, setNotice] = useState<{ id: string; text: string; ok: boolean } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(() => api.listWebhooks().then((r) => setHooks(r.webhooks))
    .catch((err) => setError(errorText(err, t('webhooks.loadFailed', 'Could not load the webhooks.')))), [t]);
  useEffect(() => { load(); }, [load]);

  const showDeliveries = async (id: string) => {
    if (open === id) { setOpen(null); return; }
    setOpen(id);
    setDeliveries((await api.listWebhookDeliveries(id)).deliveries);
  };

  const add = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      const { secret } = await api.createWebhook(url.trim(), events, description.trim());
      setCreated({ url: url.trim(), secret });
      setUrl('');
      setDescription('');
      await load();
    } catch (err) {
      setError(errorText(err, t('webhooks.createFailed', 'Could not add the webhook.')));
    } finally {
      setBusy(false);
    }
  };

  const act = async (hook: Webhook, action: 'test' | 'toggle' | 'delete') => {
    setError('');
    setNotice(null);
    try {
      if (action === 'test') {
        const r = await api.testWebhook(hook.id);
        setNotice({ id: hook.id, ok: r.ok, text: r.ok
          ? t('webhooks.testOk', 'Delivered: the endpoint answered HTTP {{code}}.', { code: r.status_code })
          : t('webhooks.testFailed', 'Not delivered: {{error}} It will be retried.', { error: r.error }) });
      } else if (action === 'toggle') {
        await api.updateWebhook(hook.id, { active: !hook.active });
      } else {
        await api.deleteWebhook(hook.id);
      }
      await load();
      if (open === hook.id && action !== 'delete') setDeliveries((await api.listWebhookDeliveries(hook.id)).deliveries);
    } catch (err) {
      setError(errorText(err, t('webhooks.actionFailed', 'That did not work.')));
    }
  };

  const toggleEvent = (value: WebhookEvent) =>
    setEvents((current) => (current.includes(value) ? current.filter((e) => e !== value) : [...current, value]));

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
      <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-1">{t('webhooks.title', 'Webhooks')}</h2>
      <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">
        {t('webhooks.hint', 'SCIRM sends a signed POST to your endpoint when a new public record matches one of your suppliers. Only records first seen after you add an endpoint are sent.')}
      </p>
      {error && <p className="text-sm text-red-600 mb-3">{error}</p>}

      <form onSubmit={add} className="space-y-2 mb-4">
        <div className="flex flex-wrap gap-2">
          <input required type="url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://your-system.example.com/scirm"
            aria-label={t('webhooks.url', 'Endpoint URL')}
            className="flex-1 min-w-[260px] px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm bg-white dark:bg-gray-800 dark:text-white" />
          <input value={description} maxLength={200} onChange={(e) => setDescription(e.target.value)}
            placeholder={t('webhooks.description', 'Description (optional)')}
            className="w-56 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm bg-white dark:bg-gray-800 dark:text-white" />
        </div>
        <div className="flex flex-wrap items-center gap-4">
          {EVENTS.map((ev) => (
            <label key={ev.value} className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300" title={ev.hint}>
              <input type="checkbox" checked={events.includes(ev.value)} onChange={() => toggleEvent(ev.value)} />
              {t(`webhooks.event.${ev.value}`, ev.label)}
            </label>
          ))}
          <button type="submit" disabled={busy || events.length === 0}
            className="ml-auto px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50">
            {t('webhooks.add', 'Add endpoint')}
          </button>
        </div>
      </form>

      {created && (
        <div className="border border-amber-300 bg-amber-50 rounded-lg p-3 mb-4 text-xs text-amber-900">
          <p className="font-medium">{t('webhooks.secretFor', 'Signing secret for {{url}}', { url: created.url })}</p>
          <input readOnly value={created.secret} onFocus={(e) => e.currentTarget.select()}
            className="w-full mt-2 px-2 py-1 border border-amber-300 rounded bg-white font-mono text-[11px]" />
          <p className="mt-2">{t('webhooks.secretOnce', 'Copy it now: it will not be shown again. Use it to check the SCIRM-Signature header (see the documentation).')}</p>
        </div>
      )}

      {hooks.length > 0 && (
        <table className="min-w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-gray-500 dark:text-gray-400 uppercase">
              <th className="py-2">{t('webhooks.endpoint', 'Endpoint')}</th>
              <th className="py-2">{t('webhooks.last', 'Last delivery')}</th>
              <th className="py-2" />
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
            {hooks.map((h) => (
              <Fragment key={h.id}>
                <tr className={h.active ? '' : 'opacity-60'}>
                  <td className="py-2">
                    <p className="font-mono text-xs text-gray-900 dark:text-white break-all">{h.url}</p>
                    <p className="text-xs text-gray-500">
                      {h.description && `${h.description} · `}{h.events.join(', ')}{!h.active && ` · ${t('webhooks.paused', 'paused')}`}
                    </p>
                    {notice?.id === h.id && <p className={`text-xs mt-1 ${notice.ok ? 'text-green-600' : 'text-red-600'}`}>{notice.text}</p>}
                  </td>
                  <td className="py-2 text-xs">
                    {h.last_delivery ? (
                      <span className={h.last_delivery.ok ? 'text-green-700' : 'text-red-600'}>
                        {h.last_delivery.ok ? t('webhooks.ok', 'OK') : t('webhooks.failed', 'Failed')}
                        {h.last_delivery.status_code != null && ` · ${h.last_delivery.status_code}`}
                        <span className="block text-gray-500">{utcDate(h.last_delivery.at).toLocaleString()}</span>
                      </span>
                    ) : <span className="text-gray-400">{t('webhooks.none', 'none yet')}</span>}
                  </td>
                  <td className="py-2 text-right whitespace-nowrap space-x-3 text-xs">
                    <button type="button" className="text-blue-600 hover:underline" onClick={() => act(h, 'test')}>{t('webhooks.test', 'Send test')}</button>
                    <button type="button" className="text-blue-600 hover:underline" onClick={() => showDeliveries(h.id)}>{t('webhooks.history', 'History')}</button>
                    <button type="button" className="text-blue-600 hover:underline" onClick={() => act(h, 'toggle')}>
                      {h.active ? t('webhooks.pause', 'Pause') : t('webhooks.resume', 'Resume')}
                    </button>
                    <button type="button" className="text-red-600 hover:underline" onClick={() => act(h, 'delete')}>{t('webhooks.delete', 'Delete')}</button>
                  </td>
                </tr>
                {open === h.id && (
                  <tr>
                    <td colSpan={3} className="pb-3">
                      {deliveries.length === 0 ? <p className="text-xs text-gray-500">{t('webhooks.noHistory', 'Nothing sent yet.')}</p> : (
                        <ul className="text-xs text-gray-600 dark:text-gray-300 space-y-0.5">
                          {deliveries.map((d) => (
                            <li key={d.id}>
                              {utcDate(d.created_at).toLocaleString()} · {d.type} · {d.status}
                              {d.last_status_code != null && ` · HTTP ${d.last_status_code}`} · {t('webhooks.attempts', '{{n}} attempt(s)', { n: d.attempts })}
                              {d.status === 'pending' && d.attempts > 0 && ` · ${t('webhooks.retry', 'retry {{at}}', { at: utcDate(d.next_attempt_at).toLocaleTimeString() })}`}
                              {d.last_error && <span className="text-red-600"> · {d.last_error}</span>}
                            </li>
                          ))}
                        </ul>
                      )}
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
