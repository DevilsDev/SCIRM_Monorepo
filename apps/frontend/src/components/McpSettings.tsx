import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { api, ApiKey, MCP_URL } from '../services/api';
import { utcDate } from '../services/time';

function errorText(err: any, fallback: string): string {
  return err?.response?.data?.detail || fallback;
}

/** The command that connects Claude Code to this SCIRM (the key is shown once). */
export function claudeCommand(key: string): string {
  return `claude mcp add --transport http scirm ${MCP_URL} --header "Authorization: Bearer ${key}"`;
}

// MCP: let an AI agent (Claude, or another MCP client) read SCIRM and propose changes (admins).
export default function McpSettings() {
  const { t } = useTranslation();
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [name, setName] = useState('Claude');
  const [created, setCreated] = useState('');
  const [error, setError] = useState('');

  const load = useCallback(() => api.listApiKeys().then((r) => setKeys(r.api_keys.filter((k) => k.scopes.includes('mcp'))))
    .catch((err) => setError(errorText(err, t('mcp.loadFailed', 'Could not load the MCP keys.')))), [t]);
  useEffect(() => { load(); }, [load]);

  const create = async () => {
    setError('');
    try {
      const { key } = await api.createApiKey(name.trim() || 'MCP client', 90, 'mcp');
      setCreated(key);
      await load();
    } catch (err) { setError(errorText(err, t('mcp.createFailed', 'Could not create the key.'))); }
  };
  const revoke = async (k: ApiKey) => {
    setError('');
    try { await api.revokeApiKey(k.id); await load(); } catch (err) { setError(errorText(err, t('mcp.revokeFailed', 'Could not revoke the key.'))); }
  };

  const active = keys.filter((k) => !k.revoked_at);
  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
      <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-1">{t('mcp.title', 'AI agents (MCP)')}</h2>
      <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
        {t('mcp.hint', 'Connect an AI agent such as Claude: it can look up suppliers, their public records, cited answers, the regulatory watch and incidents. Changes it suggests follow your')}{' '}
        <Link to="/ai-control" className="text-blue-600 hover:underline">{t('mcp.policy', 'AI action policy')}</Link>.
      </p>
      <p className="text-xs text-gray-600 dark:text-gray-300 mb-3">
        {t('mcp.url', 'Server URL (Streamable HTTP):')} <code className="font-mono bg-gray-100 dark:bg-gray-700 px-1 rounded select-all">{MCP_URL}</code>
      </p>
      {error && <p className="text-sm text-red-600 mb-3">{error}</p>}
      {created && (
        <div className="border border-amber-300 bg-amber-50 rounded-lg p-3 mb-3 text-xs text-amber-900">
          <p className="font-medium">{t('mcp.command', 'Connect Claude Code (the key is shown once):')}</p>
          <input readOnly value={claudeCommand(created)} onFocus={(e) => e.currentTarget.select()}
            className="w-full mt-2 px-2 py-1 border border-amber-300 rounded bg-white font-mono text-[11px]" />
          <p className="mt-2">{t('mcp.once', 'Other MCP clients: send the key as "Authorization: Bearer <key>". It expires in 90 days and can only call the MCP server.')}</p>
        </div>
      )}
      {active.length > 0 && (
        <ul className="text-sm divide-y divide-gray-100 dark:divide-gray-700 mb-3">
          {active.map((k) => (
            <li key={k.id} className="py-2 flex items-center justify-between">
              <span>
                {k.name} <span className="font-mono text-xs">{k.prefix}…</span>
                <span className="text-xs text-gray-500"> · {k.last_used_at
                  ? t('mcp.lastUsed', 'last used {{at}}', { at: utcDate(k.last_used_at).toLocaleString() })
                  : t('mcp.unused', 'not used yet')}</span>
              </span>
              <button type="button" onClick={() => revoke(k)} className="text-xs text-red-600 hover:underline">{t('mcp.revoke', 'Revoke')}</button>
            </li>
          ))}
        </ul>
      )}
      <div className="flex gap-2">
        <input value={name} onChange={(e) => setName(e.target.value)} maxLength={100} aria-label={t('mcp.name', 'Key name')}
          className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm bg-white dark:bg-gray-800 dark:text-white" />
        <button type="button" onClick={create} className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700">
          {t('mcp.create', 'Create MCP key')}
        </button>
      </div>
    </div>
  );
}
