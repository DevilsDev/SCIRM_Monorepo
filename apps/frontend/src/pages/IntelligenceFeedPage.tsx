import { useEffect, useState } from 'react';
import { api } from '../services/api';
import SeverityBadge from '../components/SeverityBadge';

interface IntelDoc {
  id: string;
  source: string;
  title: string;
  content: string;
  severity: string;
  region: string;
  ingested_at: string;
}

const SOURCE_COLORS: Record<string, string> = {
  news: 'bg-blue-100 text-blue-800',
  weather: 'bg-cyan-100 text-cyan-800',
  regulatory: 'bg-purple-100 text-purple-800',
  financial: 'bg-green-100 text-green-800',
};

export default function IntelligenceFeedPage() {
  const [docs, setDocs] = useState<IntelDoc[]>([]);
  const [loading, setLoading] = useState(true);
  const [sourceFilter, setSourceFilter] = useState('');
  const [ingesting, setIngesting] = useState(false);

  const fetchDocs = () => {
    setLoading(true);
    api.getIntelligenceFeed(sourceFilter || undefined)
      .then((data) => setDocs(data.documents || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchDocs(); }, [sourceFilter]);

  const handleIngest = async () => {
    setIngesting(true);
    try {
      await api.triggerIngestion();
      fetchDocs();
    } catch {} finally {
      setIngesting(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Intelligence Feed</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">Real-time supply chain intelligence from news, weather, regulatory, and financial sources</p>
        </div>
        <button
          onClick={handleIngest}
          disabled={ingesting}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
        >
          {ingesting ? 'Ingesting...' : 'Refresh Feed'}
        </button>
      </div>

      <div className="flex gap-2">
        {['', 'news', 'weather', 'regulatory', 'financial'].map((src) => (
          <button
            key={src}
            onClick={() => setSourceFilter(src)}
            className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors capitalize ${
              sourceFilter === src ? 'bg-blue-100 text-blue-800 border-blue-300' : 'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700'
            }`}
          >
            {src || 'All Sources'}
          </button>
        ))}
      </div>

      {loading ? (
        <p className="text-sm text-gray-400">Loading intelligence feed...</p>
      ) : docs.length === 0 ? (
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-8 text-center">
          <p className="text-sm text-gray-400">No intelligence documents. Click "Refresh Feed" to ingest data from all sources.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {docs.map((doc) => (
            <div key={doc.id} className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-5">
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase ${SOURCE_COLORS[doc.source] || 'bg-gray-100 dark:bg-gray-700 text-gray-800'}`}>
                      {doc.source}
                    </span>
                    <SeverityBadge severity={doc.severity} />
                    <span className="text-xs text-gray-400">{doc.region}</span>
                  </div>
                  <h3 className="text-sm font-semibold text-gray-900 dark:text-white mt-1">{doc.title}</h3>
                  <p className="text-xs text-gray-600 dark:text-gray-300 mt-1 leading-relaxed">{doc.content}</p>
                </div>
              </div>
              <p className="text-[10px] text-gray-400 mt-3">{new Date(doc.ingested_at).toLocaleString()}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
