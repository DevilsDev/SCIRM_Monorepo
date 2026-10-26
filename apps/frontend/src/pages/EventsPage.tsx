import { useEffect, useState, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { PlusIcon } from '@heroicons/react/24/outline';
import { api } from '../services/api';
import SeverityBadge from '../components/SeverityBadge';
import { formatTotals, sumByCurrency } from '../services/money';
import { Modal } from '../components/ui';
import EventForm from '../components/forms/EventForm';
import { useToast } from '../components/Toast';

interface RiskEvent {
  id: string;
  event_type: string;
  title: string;
  description: string;
  severity: string;
  affected_region: string;
  status: string;
  detected_at: string;
}

interface EventImpact {
  impacted_entity_name: string;
  impact_severity: string;
  estimated_disruption_days: number;
  /** The supplier's 12-month spend per currency (SAP spend import), when known. */
  spend_12m?: Record<string, string> | null;
  tier_distance: number;
}

export default function EventsPage() {
  const [events, setEvents] = useState<RiskEvent[]>([]);
  const [selectedEvent, setSelectedEvent] = useState<RiskEvent | null>(null);
  const [impacts, setImpacts] = useState<EventImpact[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const { t } = useTranslation();
  const { addToast } = useToast();

  const fetchEvents = useCallback(() => {
    setLoading(true);
    api.getEvents()
      .then((data) => setEvents(data.events || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { fetchEvents(); }, [fetchEvents]);

  const handleCreateEvent = async (values: any) => {
    await api.createEvent(values);
    addToast('success', t('events.created', 'Event created'), t('events.createdDesc', 'Risk event has been recorded'));
    setShowCreateModal(false);
    fetchEvents();
  };

  const handleEventClick = async (event: RiskEvent) => {
    setSelectedEvent(event);
    try {
      const data = await api.getEventImpacts(event.id);
      setImpacts(data.impacts || []);
    } catch {
      setImpacts([]);
    }
  };

  const spendAtStake = sumByCurrency(impacts.map((i) => i.spend_12m));

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{t('events.title', 'Risk Events')}</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">{t('events.subtitle', 'Track disruption events and their cascading impact through the supply chain')}</p>
        </div>
        <button
          onClick={() => setShowCreateModal(true)}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors"
        >
          <PlusIcon className="h-4 w-4" />
          {t('events.createEvent', 'Create Event')}
        </button>
      </div>

      {/* Create Event Modal */}
      <Modal
        open={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        title={t('events.createEvent', 'Create Event')}
        description={t('events.createDesc', 'Record a new supply chain disruption event')}
        size="lg"
      >
        <EventForm onSubmit={handleCreateEvent} onCancel={() => setShowCreateModal(false)} />
      </Modal>

      {loading ? (
        <p className="text-sm text-gray-400">{t('common.loading', 'Loading...')}</p>
      ) : events.length === 0 ? (
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-8 text-center">
          <p className="text-sm text-gray-400">{t('events.noEvents', 'No risk events recorded. Events are auto-generated during assessments or can be created via API.')}</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Event Timeline */}
          <div className="space-y-3">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">{t('events.timeline', 'Event Timeline')}</h2>
            {events.map((event) => (
              <div
                key={event.id}
                onClick={() => handleEventClick(event)}
                className={`bg-white dark:bg-gray-800 rounded-xl shadow-sm border p-4 cursor-pointer transition-all hover:shadow-md ${
                  selectedEvent?.id === event.id ? 'border-blue-500 ring-2 ring-blue-100' : 'border-gray-200 dark:border-gray-700'
                }`}
              >
                <div className="flex items-start justify-between">
                  <div>
                    <h3 className="text-sm font-semibold text-gray-900 dark:text-white">{event.title}</h3>
                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-1 capitalize">{event.event_type?.replace('_', ' ')} — {event.affected_region || 'Global'}</p>
                  </div>
                  <SeverityBadge severity={event.severity} />
                </div>
                {event.description && <p className="text-xs text-gray-600 dark:text-gray-300 mt-2">{event.description.slice(0, 120)}</p>}
                <p className="text-xs text-gray-400 mt-2">{new Date(event.detected_at).toLocaleString()}</p>
              </div>
            ))}
          </div>

          {/* Impact Panel */}
          <div>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">
              {selectedEvent ? `${t('events.impact', 'Impact')}: ${selectedEvent.title}` : t('events.selectEvent', 'Select an event to see impacts')}
            </h2>
            {selectedEvent && impacts.length > 0 ? (
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-center">
                    <p className="text-2xl font-bold text-red-700">{impacts.length}</p>
                    <p className="text-xs text-red-600">{t('events.entitiesImpacted', 'Entities Impacted')}</p>
                  </div>
                  <div className="bg-orange-50 border border-orange-200 rounded-xl p-4 text-center">
                    <p className="text-lg font-bold text-orange-700">{formatTotals(spendAtStake, t('events.noSpend', 'no spend data'))}</p>
                    <p className="text-xs text-orange-600">{t('events.spendAtStake', '12-month spend with these suppliers (per currency)')}</p>
                  </div>
                </div>
                {impacts.map((impact, i) => (
                  <div key={i} className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-4">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm font-medium text-gray-900 dark:text-white">{impact.impacted_entity_name}</p>
                        <p className="text-xs text-gray-500 dark:text-gray-400">{t('events.tier', 'Tier {{n}}', { n: impact.tier_distance })}</p>
                      </div>
                      <div className="text-right">
                        <SeverityBadge severity={impact.impact_severity} />
                        <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">{formatTotals(sumByCurrency([impact.spend_12m]))}</p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : selectedEvent ? (
              <p className="text-sm text-gray-400">{t('events.noImpacts', 'No cascading impacts detected for this event.')}</p>
            ) : (
              <div className="bg-gray-50 dark:bg-gray-900 rounded-xl p-8 text-center">
                <p className="text-sm text-gray-400">{t('events.clickEvent', 'Click an event in the timeline to see its cascading impact through the supply chain.')}</p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
