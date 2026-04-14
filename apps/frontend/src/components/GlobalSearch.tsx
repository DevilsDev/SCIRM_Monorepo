import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { MagnifyingGlassIcon } from '@heroicons/react/24/outline';

const SEARCH_ITEMS = [
  { label: 'Dashboard', path: '/dashboard', keywords: 'dashboard home overview' },
  { label: 'Risks', path: '/risks', keywords: 'risks risk list threats' },
  { label: 'Suppliers', path: '/suppliers', keywords: 'suppliers vendors supply' },
  { label: 'Components', path: '/components', keywords: 'components bom parts materials' },
  { label: 'Supply Chain Map', path: '/supply-chain', keywords: 'supply chain map network graph' },
  { label: 'Predictions', path: '/predictions', keywords: 'predictions forecast disruption 7 day' },
  { label: 'Risk Events', path: '/events', keywords: 'events incidents disruptions typhoon earthquake' },
  { label: 'Intel Feed', path: '/intelligence', keywords: 'intelligence feed news regulatory weather' },
  { label: 'Simulator', path: '/simulator', keywords: 'simulator digital twin monte carlo scenario' },
  { label: 'Procurement', path: '/procurement', keywords: 'procurement sourcing alternatives autonomous' },
  { label: 'Alerts', path: '/alerts', keywords: 'alerts warnings notifications' },
  { label: 'New Assessment', path: '/assessments/new', keywords: 'new assessment run evaluate' },
  { label: 'Recommendations', path: '/recommendations', keywords: 'recommendations actions mitigation' },
  { label: 'Supplier Alpha', path: '/suppliers', keywords: 'supplier alpha api manufacturer us' },
  { label: 'Supplier Beta', path: '/suppliers', keywords: 'supplier beta excipient europe germany' },
  { label: 'Supplier Gamma', path: '/suppliers', keywords: 'supplier gamma packaging china high risk' },
];

export default function GlobalSearch() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement>(null);

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

  const filtered = query.length > 0
    ? SEARCH_ITEMS.filter((item) => (item.label + ' ' + item.keywords).toLowerCase().includes(query.toLowerCase()))
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
        <span>Search...</span>
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
                placeholder="Search pages, suppliers, components..."
                className="flex-1 bg-transparent text-sm text-gray-900 dark:text-white outline-none placeholder:text-gray-400"
              />
              <kbd className="text-[10px] text-gray-400 bg-gray-100 dark:bg-gray-700 px-1.5 py-0.5 rounded">ESC</kbd>
            </div>
            <div className="max-h-72 overflow-y-auto p-2">
              {filtered.map((item) => (
                <button
                  key={item.label}
                  onClick={() => handleSelect(item.path)}
                  className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-left text-sm hover:bg-blue-50 dark:hover:bg-gray-700 transition-colors"
                >
                  <span className="text-gray-900 dark:text-white font-medium">{item.label}</span>
                </button>
              ))}
              {filtered.length === 0 && (
                <p className="px-3 py-4 text-sm text-gray-400 text-center">No results for "{query}"</p>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
