import { FormEvent, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '../contexts/AuthContext';
import { api, SapConnection, SapConnectionTest } from '../services/api';

/** Whether a test result or import outcome is worth showing as "last checked". */
export function connectionState(connection: SapConnection | null): 'none' | 'untested' | 'ok' | 'failing' {
  if (!connection) return 'none';
  if (!connection.last_test) return 'untested';
  return connection.last_test.ok ? 'ok' : 'failing';
}

// The organization's SAP S/4HANA connection. Admins set it up; everyone can see whether
// it works. The password is sent once and never shown again.
export default function SapConnectionPanel({ connection, onChange }: {
  connection: SapConnection | null; onChange: (c: SapConnection | null) => void;
}) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const isAdmin = !!user?.roles?.includes('admin');
  const [editing, setEditing] = useState(false);
  const [baseUrl, setBaseUrl] = useState(connection?.base_url || '');
  const [client, setClient] = useState(connection?.sap_client || '');
  const [username, setUsername] = useState(connection?.username || '');
  const [password, setPassword] = useState('');
  const [test, setTest] = useState<SapConnectionTest | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const detail = (err: any, fallback: string) => err?.response?.data?.detail || fallback;

  const startEdit = () => {
    setBaseUrl(connection?.base_url || '');
    setClient(connection?.sap_client || '');
    setUsername(connection?.username || '');
    setPassword('');
    setEditing(true);
  };

  const save = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      const saved = await api.saveSapConnection({ base_url: baseUrl.trim(), sap_client: client.trim() || undefined,
        username: username.trim(), password: password || undefined });
      setPassword('');
      setEditing(false);
      onChange(saved);
      setTest(await api.testSapConnection());
      onChange(await api.getSapConnection());
    } catch (err) {
      setError(detail(err, t('sapConn.saveFailed', 'The connection could not be saved.')));
    } finally {
      setBusy(false);
    }
  };

  const runTest = async () => {
    setBusy(true);
    setError('');
    try {
      setTest(await api.testSapConnection());
      onChange(await api.getSapConnection());
    } catch (err) {
      setError(detail(err, t('sapConn.testFailed', 'The test could not be run.')));
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    setBusy(true);
    setError('');
    try {
      await api.deleteSapConnection();
      setTest(null);
      onChange(null);
    } catch (err) {
      setError(detail(err, t('sapConn.removeFailed', 'The connection could not be removed.')));
    } finally {
      setBusy(false);
    }
  };

  const shownTest = test || connection?.last_test || null;
  const state = connectionState(connection);
  const card = 'bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6';
  const input = 'w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm bg-white dark:bg-gray-800';
  const button = 'px-4 py-2 rounded-lg text-sm font-medium disabled:opacity-50';
  const showForm = isAdmin && (editing || !connection);

  return (
    <div className={card}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">{t('sapConn.title', 'SAP connection')}</h2>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            {t('sapConn.intro', 'SAP S/4HANA only: SCIRM reads suppliers and purchase orders through the standard OData APIs (API_BUSINESS_PARTNER, API_PURCHASEORDER_PROCESS_SRV) with a communication user that can only read. It never writes to SAP. On SAP ECC, use the file imports below.')}
          </p>
        </div>
        {state !== 'none' && (
          <span className={`px-2 py-1 rounded-full text-xs ${state === 'ok' ? 'bg-green-100 text-green-800'
            : state === 'failing' ? 'bg-red-100 text-red-800' : 'bg-gray-100 text-gray-700'}`}>
            {state === 'ok' ? t('sapConn.ok', 'Working') : state === 'failing' ? t('sapConn.failing', 'Not working')
              : t('sapConn.untested', 'Not tested')}
          </span>
        )}
      </div>

      {connection && !editing && (
        <dl className="mt-4 grid grid-cols-1 sm:grid-cols-3 gap-2 text-sm">
          <div><dt className="text-xs text-gray-500">{t('sapConn.address', 'Address')}</dt><dd className="break-all">{connection.base_url}</dd></div>
          <div><dt className="text-xs text-gray-500">{t('sapConn.client', 'SAP client')}</dt><dd>{connection.sap_client || '–'}</dd></div>
          <div><dt className="text-xs text-gray-500">{t('sapConn.user', 'Communication user')}</dt><dd>{connection.username}</dd></div>
        </dl>
      )}

      {!connection && !isAdmin && (
        <p className="text-sm text-gray-600 mt-4">{t('sapConn.askAdmin', 'No SAP connection is set up. An administrator can set one up here.')}</p>
      )}

      {showForm && (
        <form onSubmit={save} className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-3">
          <label className="text-xs text-gray-700 dark:text-gray-300 sm:col-span-2">
            {t('sapConn.address', 'Address')}
            <input className={input} value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} required
              placeholder="https://my-s4.example.com" type="url" maxLength={500} />
            <span className="text-gray-500">{t('sapConn.addressHint', 'The system\'s public HTTPS address, without /sap/opu/odata. Systems only reachable inside your network need a public endpoint, such as SAP API Management or SAP BTP.')}</span>
          </label>
          <label className="text-xs text-gray-700 dark:text-gray-300">
            {t('sapConn.client', 'SAP client')}
            <input className={input} value={client} onChange={(e) => setClient(e.target.value)} placeholder="100"
              inputMode="numeric" maxLength={3} />
          </label>
          <label className="text-xs text-gray-700 dark:text-gray-300">
            {t('sapConn.user', 'Communication user')}
            <input className={input} value={username} onChange={(e) => setUsername(e.target.value)} required
              autoComplete="off" maxLength={200} />
          </label>
          <label className="text-xs text-gray-700 dark:text-gray-300 sm:col-span-2">
            {t('sapConn.password', 'Password')}
            <input className={input} value={password} onChange={(e) => setPassword(e.target.value)} type="password"
              autoComplete="new-password" required={!connection} maxLength={500}
              placeholder={connection ? t('sapConn.keepPassword', 'Leave empty to keep the stored password') : ''} />
            <span className="text-gray-500">{t('sapConn.passwordHint', 'Stored encrypted and never shown again. In S/4HANA Cloud, give the communication user the arrangements SAP_COM_0008 and SAP_COM_0053.')}</span>
          </label>
          <div className="flex gap-2 sm:col-span-2">
            <button type="submit" disabled={busy} className={`${button} bg-blue-600 text-white hover:bg-blue-700`}>
              {busy ? t('sap.working', 'Working...') : t('sapConn.saveAndTest', 'Save and test')}
            </button>
            {connection && (
              <button type="button" onClick={() => setEditing(false)} className={`${button} border border-gray-300`}>
                {t('common.cancel', 'Cancel')}
              </button>
            )}
          </div>
        </form>
      )}

      {connection && isAdmin && !editing && (
        <div className="flex flex-wrap gap-2 mt-4">
          <button type="button" disabled={busy} onClick={runTest} className={`${button} bg-blue-600 text-white hover:bg-blue-700`}>
            {busy ? t('sap.working', 'Working...') : t('sapConn.test', 'Test connection')}
          </button>
          <button type="button" disabled={busy} onClick={startEdit} className={`${button} border border-gray-300`}>
            {t('sapConn.edit', 'Change settings')}
          </button>
          <button type="button" disabled={busy} onClick={remove} className={`${button} text-red-600 hover:underline`}>
            {t('sapConn.remove', 'Remove connection')}
          </button>
        </div>
      )}

      {shownTest && (
        <ul className="mt-4 space-y-1 text-xs">
          {shownTest.checks.map((c) => (
            <li key={c.service} className={c.ok ? 'text-green-700' : 'text-red-700'}>
              <span className="font-mono">{c.service}</span>: {c.ok ? t('sapConn.readable', 'readable') : c.detail}
            </li>
          ))}
        </ul>
      )}
      {connection?.last_import && !connection.last_import.ok && (
        <p className="text-xs text-red-700 mt-2">
          {t('sapConn.lastImportFailed', 'The last import from SAP failed: {{error}}', { error: connection.last_import.error })}
        </p>
      )}
      {error && <p className="text-sm text-red-600 mt-3">{error}</p>}
    </div>
  );
}
