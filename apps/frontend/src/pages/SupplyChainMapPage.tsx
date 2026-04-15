import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api } from '../services/api';
import SupplyChainFlow from '../components/d3/SupplyChainFlow';

interface MapNode {
  id: string;
  type: string;
  label: string;
  risk_score?: number;
  risk_tier?: string;
  severity?: string;
}

interface MapEdge {
  source: string;
  target: string;
  relationship: string;
}

export default function SupplyChainMapPage() {
  const [nodes, setNodes] = useState<MapNode[]>([]);
  const [edges, setEdges] = useState<MapEdge[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const { t } = useTranslation();

  useEffect(() => {
    api
      .getSupplyChainMap()
      .then((data) => {
        setNodes(data.nodes || []);
        setEdges(data.edges || []);
      })
      .catch((err) => setError(err.message || 'Failed to load supply chain map'))
      .finally(() => setLoading(false));
  }, []);

  const suppliers = nodes.filter((n) => n.type === 'supplier').length;
  const risks = nodes.filter((n) => n.type === 'risk').length;
  const orgs = nodes.filter((n) => n.type === 'organization').length;

  if (loading) return <p className="text-sm text-gray-400">{t('common.loading', 'Loading...')}</p>;
  if (error) return <p className="text-sm text-red-500">{error}</p>;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{t('supplyChain.title', 'Supply Chain Map')}</h1>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
          {t('supplyChain.subtitle', 'Tiered flow — suppliers → organization → risks. Link thickness = risk magnitude.')}
        </p>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 text-center">
          <p className="text-3xl font-bold text-blue-700">{orgs}</p>
          <p className="text-xs text-blue-600">{t('supplyChain.organizations', 'Organizations')}</p>
        </div>
        <div className="bg-green-50 border border-green-200 rounded-xl p-4 text-center">
          <p className="text-3xl font-bold text-green-700">{suppliers}</p>
          <p className="text-xs text-green-600">{t('supplyChain.suppliers', 'Suppliers')}</p>
        </div>
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-center">
          <p className="text-3xl font-bold text-red-700">{risks}</p>
          <p className="text-xs text-red-600">{t('supplyChain.activeRisks', 'Active Risks')}</p>
        </div>
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6 overflow-visible">
        <SupplyChainFlow nodes={nodes} edges={edges} height={720} />
      </div>

      <div className="flex gap-6 text-xs text-gray-500 dark:text-gray-400">
        <div className="flex items-center gap-2"><div className="w-4 h-4 rounded-full bg-blue-500" /> {t('supplyChain.legendSupplier', 'Supplier')}</div>
        <div className="flex items-center gap-2"><div className="w-4 h-4 rounded-full bg-purple-500" /> {t('supplyChain.legendOrganization', 'Organization')}</div>
        <div className="flex items-center gap-2"><div className="w-4 h-4 rounded-full bg-red-500" /> {t('supplyChain.legendRisk', 'Risk')}</div>
        <div className="ml-4 flex items-center gap-2"><div className="w-6 h-1 bg-green-400 rounded" /> {t('supplyChain.legendLow', 'Low Risk')}</div>
        <div className="flex items-center gap-2"><div className="w-6 h-1 bg-yellow-400 rounded" /> {t('supplyChain.legendMedium', 'Medium')}</div>
        <div className="flex items-center gap-2"><div className="w-6 h-1 bg-orange-400 rounded" /> {t('supplyChain.legendHigh', 'High')}</div>
        <div className="flex items-center gap-2"><div className="w-6 h-2 bg-red-400 rounded" /> {t('supplyChain.legendCritical', 'Critical (thicker = higher risk)')}</div>
      </div>
    </div>
  );
}
