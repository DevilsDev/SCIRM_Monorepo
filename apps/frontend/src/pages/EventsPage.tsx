import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api } from '../services/api';
import SeverityBadge from '../components/SeverityBadge';

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
  estimated_financial_impact: number;
  tier_distance: number;
}

export default function EventsPage() {
  const [events, setEvents] = useState<RiskEvent[]>([]);
  const [selectedEvent, setSelectedEvent] = useState<RiskEvent | null>(null);
  const [impacts, setImpacts] = useState<EventImpact[]>([]);
  const [loading, setLoading] = useState(true);
  const { t } = useTranslation();

  useEffect(() => {
    api.getEvents()
      .then((data) => setEvents(data.events || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const handleEventClick = async (event: RiskEvent) => {
    setSelectedEvent(event);
    try {
      const data = await api.getEventImpacts(event.id);
      setImpacts(data.impacts || []);
    } catch {
      setImpacts([]);
    }
  };

  const totalFinancialImpact = impacts.reduce((s, i) => s + (i.estimated_financial_impact || 0), 0);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{t('events.title', 'Risk Events')}</h1>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">{t('events.subtitle', 'Track disruption events and their cascading impact through the supply chain')}</p>
      </div>

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
                    <p className="text-2xl font-bold text-orange-700">${(totalFinancialImpact / 1000).toFixed(0)}k</p>
                    <p className="text-xs text-orange-600">{t('events.estFinancialImpact', 'Est. Financial Impact')}</p>
                  </div>
                </div>
                {impacts.map((impact, i) => (
                  <div key={i} className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-4">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm font-medium text-gray-900 dark:text-white">{impact.impacted_entity_name}</p>
                        <p className="text-xs text-gray-500 dark:text-gray-400">Tier {impact.tier_distance} — {impact.estimated_disruption_days}d disruption</p>
                      </div>
                      <div className="text-right">
                        <SeverityBadge severity={impact.impact_severity} />
                        <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">${(impact.estimated_financial_impact / 1000).toFixed(0)}k</p>
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
