import { useEffect, useState } from 'react';
import { BellIcon } from '@heroicons/react/24/outline';
import { useNavigate } from 'react-router-dom';
import { api } from '../services/api';

export default function NotificationBell() {
  const [count, setCount] = useState(0);
  const [open, setOpen] = useState(false);
  const [alerts, setAlerts] = useState<any[]>([]);
  const navigate = useNavigate();

  useEffect(() => {
    const fetchAlerts = () => {
      api.getAlerts({ status: 'active' })
        .then((data) => {
          const active = data.alerts || [];
          setAlerts(active.slice(0, 5));
          setCount(active.length);
        })
        .catch(() => {});
    };
    fetchAlerts();
    const interval = setInterval(fetchAlerts, 30000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="relative p-1.5 rounded-lg hover:bg-gray-700 transition-colors"
        aria-label="Notifications"
      >
        <BellIcon className="h-5 w-5 text-gray-400" />
        {count > 0 && (
          <span className="absolute -top-0.5 -right-0.5 h-4 w-4 bg-red-500 text-white text-[9px] font-bold rounded-full flex items-center justify-center">
            {count > 9 ? '9+' : count}
          </span>
        )}
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute left-0 top-10 z-50 w-72 bg-white dark:bg-gray-800 rounded-xl shadow-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
            <div className="px-4 py-3 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
              <span className="text-sm font-semibold text-gray-900 dark:text-white">Notifications</span>
              {count > 0 && <span className="text-xs text-red-500 font-medium">{count} active</span>}
            </div>
            <div className="max-h-60 overflow-y-auto">
              {alerts.length === 0 ? (
                <p className="px-4 py-6 text-xs text-gray-400 text-center">No active alerts</p>
              ) : (
                alerts.map((alert, i) => (
                  <div key={i} className="px-4 py-3 hover:bg-gray-50 dark:hover:bg-gray-700 cursor-pointer border-b border-gray-100 dark:border-gray-700 last:border-0"
                    onClick={() => { navigate('/alerts'); setOpen(false); }}
                  >
                    <p className="text-xs font-medium text-gray-900 dark:text-white truncate">{alert.title}</p>
                    <p className="text-[10px] text-gray-400 mt-0.5">{alert.severity} · {new Date(alert.created_at).toLocaleTimeString()}</p>
                  </div>
                ))
              )}
            </div>
            <button
              onClick={() => { navigate('/alerts'); setOpen(false); }}
              className="w-full px-4 py-2.5 text-xs text-blue-600 hover:bg-blue-50 dark:hover:bg-gray-700 font-medium border-t border-gray-200 dark:border-gray-700"
            >
              View all alerts
            </button>
          </div>
        </>
      )}
    </div>
  );
}
