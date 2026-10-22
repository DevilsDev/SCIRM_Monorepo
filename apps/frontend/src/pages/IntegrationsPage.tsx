import { ReactNode, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { api, EmbeddingStatus, PublicSourceStatus, SapConnection } from '../services/api';
import { useAuth } from '../contexts/AuthContext';
import { utcDate } from '../services/time';
import ApiKeysSettings from '../components/ApiKeysSettings';
import WebhooksSettings from '../components/WebhooksSettings';
import ReportsSettings from '../components/ReportsSettings';

type Tone = 'ok' | 'warn' | 'bad' | 'off';
const TONES: Record<Tone, string> = {
  ok: 'bg-green-100 text-green-800', warn: 'bg-amber-100 text-amber-800',
  bad: 'bg-red-100 text-red-800', off: 'bg-gray-100 text-gray-600',
};

function Badge({ tone, children }: { tone: Tone; children: ReactNode }) {
  return <span className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${TONES[tone]}`}>{children}</span>;
}

/** A public source's state: failed runs and sources not refreshed within a day stand out. */
export function sourceHealth(s: PublicSourceStatus, now: Date = new Date()): { tone: Tone; label: string } {
  if (s.status === 'never_run') return { tone: 'off', label: 'Not run yet' };
  if (s.status === 'error') return { tone: 'bad', label: 'Last run failed' };
  if (s.status === 'rate_limited') return { tone: 'warn', label: 'Rate limited' };
  const last = s.last_success_at ? utcDate(s.last_success_at) : null;
  if (!last || now.getTime() - last.getTime() > 24 * 3600 * 1000) return { tone: 'warn', label: 'Not refreshed in 24 h' };
  return { tone: 'ok', label: 'Up to date' };
}

export function sapHealth(c: SapConnection | null): { tone: Tone; label: string } {
  if (!c) return { tone: 'off', label: 'Not connected' };
  if (c.last_test && !c.last_test.ok) return { tone: 'bad', label: 'Connection test failed' };
  if (c.last_import && !c.last_import.ok) return { tone: 'bad', label: 'Last import failed' };
  if (!c.last_test) return { tone: 'warn', label: 'Not tested' };
  return { tone: 'ok', label: 'Working' };
}

function Card({ title, status, children, action }: { title: string; status?: ReactNode; children: ReactNode; action?: ReactNode }) {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
      <div className="flex items-center justify-between gap-3 mb-2">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">{title}</h2>
        <div className="flex items-center gap-3">{status}{action}</div>
      </div>
      {children}
    </div>
  );
}

// Every connection between SCIRM and other systems, and its health (administrators).
export default function IntegrationsPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const isAdmin = !!user?.roles?.includes('admin');
  const [sap, setSap] = useState<SapConnection | null | undefined>(undefined);
  const [sources, setSources] = useState<Record<string, PublicSourceStatus>>({});
  const [total, setTotal] = useState(0);
  const [embeddings, setEmbeddings] = useState<EmbeddingStatus | undefined>();
  const [error, setError] = useState('');

  useEffect(() => {
    if (!isAdmin) return;
    api.getSapConnection().then(setSap).catch(() => setSap(null));
    api.getIntelligenceSources()
      .then((r) => { setSources(r.sources); setTotal(r.total_documents); setEmbeddings(r.embeddings); })
      .catch(() => setError(t('integrations.sourcesFailed', 'Could not load the public data sources.')));
  }, [isAdmin, t]);

  if (!isAdmin) {
    return <p className="text-sm text-gray-500">{t('integrations.forbidden', 'Integrations are managed by administrators.')}</p>;
  }

  const sapState = sapHealth(sap ?? null);
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{t('integrations.title', 'Integrations')}</h1>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          {t('integrations.subtitle', 'Where SCIRM gets its data and where it sends it.')}
        </p>
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}

      <Card title={t('integrations.sap', 'SAP S/4HANA')} status={sap !== undefined && <Badge tone={sapState.tone}>{t(`integrations.sapState.${sapState.tone}`, sapState.label)}</Badge>}
        action={<Link to="/suppliers/import/sap" className="text-sm text-blue-600 hover:underline">{sap ? t('integrations.manage', 'Manage') : t('integrations.connect', 'Connect')}</Link>}>
        {sap ? (
          <dl className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-sm">
            <div><dt className="text-xs text-gray-500">{t('integrations.address', 'Address')}</dt><dd className="font-mono text-xs break-all">{sap.base_url}</dd></div>
            <div><dt className="text-xs text-gray-500">{t('integrations.lastTest', 'Last test')}</dt>
              <dd>{sap.last_test ? `${sap.last_test.ok ? 'OK' : t('integrations.failed', 'Failed')} · ${utcDate(sap.last_test.at).toLocaleString()}` : '–'}</dd></div>
            <div><dt className="text-xs text-gray-500">{t('integrations.lastImport', 'Last import')}</dt>
              <dd>{sap.last_import ? `${sap.last_import.kind} · ${sap.last_import.ok ? 'OK' : (sap.last_import.error || t('integrations.failed', 'Failed'))} · ${utcDate(sap.last_import.at).toLocaleString()}` : '–'}</dd></div>
          </dl>
        ) : (
          <p className="text-sm text-gray-500">{t('integrations.sapNone', 'Read suppliers and purchase-order spend directly from SAP, or import file extracts (SAP ECC).')}</p>
        )}
      </Card>

      <Card title={t('integrations.public', 'Public data sources')} status={<span className="text-xs text-gray-500">{t('integrations.records', '{{n}} records', { n: total.toLocaleString() })}</span>}>
        <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
          {t('integrations.publicHint', 'Checked every hour. Records are matched to your suppliers by name, and disasters by site or country.')}
        </p>
        <table className="min-w-full text-sm">
          <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
            {Object.entries(sources).map(([key, s]) => {
              const health = sourceHealth(s);
              return (
                <tr key={key}>
                  <td className="py-2 text-gray-900 dark:text-white">{s.label}</td>
                  <td className="py-2"><Badge tone={health.tone}>{t(`integrations.sourceState.${health.label}`, health.label)}</Badge></td>
                  <td className="py-2 text-xs text-gray-500">
                    {s.last_success_at ? t('integrations.lastSuccess', 'last updated {{at}}', { at: utcDate(s.last_success_at).toLocaleString() }) : ''}
                    {s.signals_new != null && s.status === 'ok' && ` · ${t('integrations.new', '{{n}} new', { n: s.signals_new })}`}
                    {s.status === 'error' && s.error && <span className="block text-red-600">{s.error}</span>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <p className="text-xs text-gray-500 mt-3">
          {embeddings?.status === 'on'
            ? t('integrations.vectorsOn', 'Meaning-based search: on ({{model}}), {{embedded}} of {{total}} records indexed.',
              { model: embeddings.model, embedded: embeddings.embedded ?? 0, total: embeddings.total ?? 0 })
            : t('integrations.vectorsOff', 'Meaning-based search: off. Answers use keyword search over the records (AWS Bedrock is not configured).')}
        </p>
      </Card>

      <ApiKeysSettings />
      <WebhooksSettings />
      <ReportsSettings />
    </div>
  );
}
