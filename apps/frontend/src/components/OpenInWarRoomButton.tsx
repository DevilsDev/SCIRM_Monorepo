import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAuth } from '../contexts/AuthContext';
import { api } from '../services/api';

// Opens a war-room incident from a public record (affected suppliers are prefilled from the
// record's matches) and goes to it. Shown to admins and analysts only.
export default function OpenInWarRoomButton({ signalId }: { signalId: string | null | undefined }) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  if (!signalId || !user?.roles?.some((r) => r === 'admin' || r === 'analyst')) return null;
  const open = async () => {
    setBusy(true); setError('');
    try {
      const opened = await api.openIncident({ signal_id: signalId });
      navigate(`/war-room?incident=${encodeURIComponent(opened.incident.id)}`);
    } catch (err: any) {
      setError(err?.response?.data?.detail || t('wr.openFailed', 'The incident could not be opened.'));
      setBusy(false);
    }
  };
  return (
    <span className="inline-flex items-center gap-2">
      <button type="button" onClick={open} disabled={busy} className="text-xs text-red-700 dark:text-red-300 hover:underline disabled:opacity-50">
        {t('wr.openFromRecord', 'Open in war room')}
      </button>
      {error && <span className="text-xs text-red-600">{error}</span>}
    </span>
  );
}
