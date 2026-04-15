import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { MagnifyingGlassIcon } from '@heroicons/react/24/outline';

const SEARCH_ITEMS = [
  { tKey: 'nav.dashboard', fallback: 'Dashboard', path: '/dashboard', keywords: 'dashboard home overview' },
  { tKey: 'nav.risks', fallback: 'Risks', path: '/risks', keywords: 'risks risk list threats' },
  { tKey: 'nav.suppliers', fallback: 'Suppliers', path: '/suppliers', keywords: 'suppliers vendors supply' },
  { tKey: 'nav.components', fallback: 'Components', path: '/components', keywords: 'components bom parts materials' },
  { tKey: 'nav.supplyChain', fallback: 'Network Map', path: '/supply-chain', keywords: 'supply chain map network graph' },
  { tKey: 'nav.predictions', fallback: 'Predictions', path: '/predictions', keywords: 'predictions forecast disruption 7 day' },
  { tKey: 'nav.events', fallback: 'Risk Events', path: '/events', keywords: 'events incidents disruptions typhoon earthquake' },
  { tKey: 'nav.intelFeed', fallback: 'Intel Feed', path: '/intelligence', keywords: 'intelligence feed news regulatory weather' },
  { tKey: 'nav.simulator', fallback: 'Simulator', path: '/simulator', keywords: 'simulator digital twin monte carlo scenario' },
  { tKey: 'nav.procurement', fallback: 'Procurement', path: '/procurement', keywords: 'procurement sourcing alternatives autonomous' },
  { tKey: 'nav.alerts', fallback: 'Alerts', path: '/alerts', keywords: 'alerts warnings notifications' },
  { tKey: 'nav.newAssessment', fallback: 'New Assessment', path: '/assessments/new', keywords: 'new assessment run evaluate' },
  { tKey: 'nav.recommendations', fallback: 'Recommendations', path: '/recommendations', keywords: 'recommendations actions mitigation' },
];

export default function GlobalSearch() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement>(null);
  const { t } = useTranslation();

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setOpen(true);
      }
      if (e.key === 'Escape') setOpen(false);
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  const getLabel = (item: typeof SEARCH_ITEMS[0]) => t(item.tKey, item.fallback);

  const filtered = query.length > 0
    ? SEARCH_ITEMS.filter((item) => (getLabel(item) + ' ' + item.fallback + ' ' + item.keywords).toLowerCase().includes(query.toLowerCase()))
    : SEARCH_ITEMS.slice(0, 6);

  const handleSelect = (path: string) => {
    navigate(path);
    setOpen(false);
    setQuery('');
  };

  return (
    <>
      {/* Search trigger */}
      <button
        onClick={() => setOpen(true)}
        className="w-full flex items-center gap-2 px-3 py-2 rounded-lg bg-gray-800 text-gray-400 text-xs hover:bg-gray-700 transition-colors"
      >
        <MagnifyingGlassIcon className="h-4 w-4" />
        <span>{t('common.search', 'Search...')}</span>
        <kbd className="ml-auto text-[10px] bg-gray-700 px-1.5 py-0.5 rounded">⌘K</kbd>
      </button>

      {/* Search modal */}
      {open && (
        <div className="fixed inset-0 z-50 flex items-start justify-center pt-[20vh]" onClick={() => setOpen(false)}>
          <div className="absolute inset-0 bg-black/50" />
          <div className="relative w-full max-w-lg bg-white dark:bg-gray-800 rounded-xl shadow-2xl overflow-hidden" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center gap-3 px-4 py-3 border-b border-gray-200 dark:border-gray-700">
              <MagnifyingGlassIcon className="h-5 w-5 text-gray-400" />
              <input
                ref={inputRef}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={t('common.searchPlaceholder', 'Search pages, suppliers, components...')}
                className="flex-1 bg-transparent text-sm text-gray-900 dark:text-white outline-none placeholder:text-gray-400"
              />
              <kbd className="text-[10px] text-gray-400 bg-gray-100 dark:bg-gray-700 px-1.5 py-0.5 rounded">ESC</kbd>
            </div>
            <div className="max-h-72 overflow-y-auto p-2">
              {filtered.map((item) => (
                <button
                  key={item.tKey}
                  onClick={() => handleSelect(item.path)}
                  className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-left text-sm hover:bg-blue-50 dark:hover:bg-gray-700 transition-colors"
                >
                  <span className="text-gray-900 dark:text-white font-medium">{getLabel(item)}</span>
                </button>
              ))}
              {filtered.length === 0 && (
                <p className="px-3 py-4 text-sm text-gray-400 text-center">{t('common.noResults', 'No results for "{{query}}"', { query })}</p>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
