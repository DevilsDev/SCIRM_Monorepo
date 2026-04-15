import { useEffect, useState, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { CheckCircleIcon, ChatBubbleLeftIcon } from '@heroicons/react/24/outline';
import { api, Alert } from '../services/api';
import SeverityBadge from '../components/SeverityBadge';
import { SlideOver, TextArea } from '../components/ui';
import { useToast } from '../components/Toast';

export default function AlertsPage() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [notesAlert, setNotesAlert] = useState<Alert | null>(null);
  const [noteText, setNoteText] = useState('');
  const { t } = useTranslation();
  const { addToast } = useToast();

  const fetchAlerts = useCallback(() => {
    setLoading(true);
    api
      .getAlerts({ status: statusFilter || undefined })
      .then((data) => setAlerts(data.alerts || []))
      .catch((err) => setError(err.message || 'Failed to load alerts'))
      .finally(() => setLoading(false));
  }, [statusFilter]);

  useEffect(() => { fetchAlerts(); }, [fetchAlerts]);

  const activeCount = alerts.filter((a) => a.status === 'active').length;

  const handleAcknowledge = async (alertId: string) => {
    try {
      await api.acknowledgeAlert(alertId);
      addToast('success', t('alerts.acknowledged', 'Acknowledged'), t('alerts.ackDesc', 'Alert has been acknowledged'));
      fetchAlerts();
    } catch {
      addToast('error', t('common.error', 'Error'), t('alerts.ackFailed', 'Failed to acknowledge alert'));
    }
  };

  const handleSaveNotes = () => {
    if (!notesAlert || !noteText.trim()) return;
    // Store notes in localStorage until backend supports it
    const key = `scirm_alert_notes_${notesAlert.id}`;
    const existing = JSON.parse(localStorage.getItem(key) || '[]');
    existing.push({ text: noteText, timestamp: new Date().toISOString() });
    localStorage.setItem(key, JSON.stringify(existing));
    addToast('success', t('alerts.noteSaved', 'Note saved'));
    setNoteText('');
    setNotesAlert(null);
  };

  const getNotes = (alertId: string) => {
    return JSON.parse(localStorage.getItem(`scirm_alert_notes_${alertId}`) || '[]');
  };

  const statusLabel = (status: string) => {
    const map: Record<string, string> = {
      active: t('alerts.active', 'Active'),
      acknowledged: t('alerts.acknowledged', 'Acknowledged'),
      resolved: t('alerts.resolved', 'Resolved'),
    };
    return map[status] || status;
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{t('alerts.title', 'Alerts')}</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            {t('alerts.activeCount', '{{count}} active alert(s) of {{total}} total', { count: activeCount, total: alerts.length })}
          </p>
        </div>
      </div>

      <div className="flex gap-3">
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm bg-white dark:bg-gray-800 focus:ring-2 focus:ring-blue-500 outline-none"
        >
          <option value="">{t('alerts.allStatuses', 'All Statuses')}</option>
          <option value="active">{t('alerts.active', 'Active')}</option>
          <option value="acknowledged">{t('alerts.acknowledged', 'Acknowledged')}</option>
          <option value="resolved">{t('alerts.resolved', 'Resolved')}</option>
        </select>
      </div>

      <div className="space-y-3">
        {loading ? (
          <p className="text-sm text-gray-400">{t('common.loading', 'Loading...')}</p>
        ) : error ? (
          <p className="text-sm text-red-500">{error}</p>
        ) : alerts.length === 0 ? (
          <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-8 text-center">
            <p className="text-sm text-gray-400">{t('alerts.noAlerts', 'No alerts. Run an assessment to generate risk alerts.')}</p>
          </div>
        ) : (
          alerts.map((alert) => {
            const notes = getNotes(alert.id);
            return (
              <div
                key={alert.id}
                className={`bg-white dark:bg-gray-800 rounded-xl shadow-sm border p-5 transition-colors ${
                  alert.status === 'active' ? 'border-red-200 dark:border-red-800' : 'border-gray-200 dark:border-gray-700'
                }`}
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-3">
                      <h3 className="text-sm font-semibold text-gray-900 dark:text-white">{alert.title}</h3>
                      <SeverityBadge severity={alert.severity} />
                      <span
                        className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                          alert.status === 'active'
                            ? 'bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-300'
                            : alert.status === 'acknowledged'
                            ? 'bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300'
                            : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300'
                        }`}
                      >
                        {statusLabel(alert.status)}
                      </span>
                      {notes.length > 0 && (
                        <span className="text-[10px] text-gray-400">{notes.length} note(s)</span>
                      )}
                    </div>
                    {alert.description && (
                      <p className="text-xs text-gray-600 dark:text-gray-300 mt-2">{alert.description}</p>
                    )}
                    <p className="text-xs text-gray-400 mt-2">{new Date(alert.created_at).toLocaleString()}</p>
                  </div>

                  {/* Action buttons */}
                  <div className="flex items-center gap-2 ml-4">
                    {alert.status === 'active' && (
                      <button
                        onClick={() => handleAcknowledge(alert.id)}
                        className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 text-white rounded-lg text-xs font-medium hover:bg-blue-700 transition-colors"
                      >
                        <CheckCircleIcon className="h-3.5 w-3.5" />
                        {t('alerts.acknowledge', 'Acknowledge')}
                      </button>
                    )}
                    <button
                      onClick={() => { setNotesAlert(alert); setNoteText(''); }}
                      className="p-2 text-gray-400 hover:text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-900/30 rounded-lg transition-colors"
                      title={t('alerts.addNotes', 'Add notes')}
                    >
                      <ChatBubbleLeftIcon className="h-4 w-4" />
                    </button>
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Notes SlideOver */}
      <SlideOver
        open={!!notesAlert}
        onClose={() => setNotesAlert(null)}
        title={t('alerts.notes', 'Alert Notes')}
        description={notesAlert?.title}
        width="sm"
      >
        {notesAlert && (
          <div className="space-y-4">
            {/* Existing notes */}
            {getNotes(notesAlert.id).length > 0 && (
              <div className="space-y-2">
                {getNotes(notesAlert.id).map((note: any, i: number) => (
                  <div key={i} className="p-3 bg-gray-50 dark:bg-gray-900 rounded-lg">
                    <p className="text-sm text-gray-900 dark:text-white">{note.text}</p>
                    <p className="text-[10px] text-gray-400 mt-1">{new Date(note.timestamp).toLocaleString()}</p>
                  </div>
                ))}
              </div>
            )}

            {/* New note */}
            <div className="space-y-2">
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">{t('alerts.newNote', 'Add a note')}</label>
              <TextArea
                value={noteText}
                onChange={(e) => setNoteText(e.target.value)}
                placeholder={t('alerts.notePlaceholder', 'Write your investigation notes, actions taken, etc.')}
                rows={4}
                showCount
                maxLength={500}
              />
              <button
                onClick={handleSaveNotes}
                disabled={!noteText.trim()}
                className="w-full px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors disabled:opacity-50"
              >
                {t('alerts.saveNote', 'Save Note')}
              </button>
            </div>
          </div>
        )}
      </SlideOver>
    </div>
  );
}
