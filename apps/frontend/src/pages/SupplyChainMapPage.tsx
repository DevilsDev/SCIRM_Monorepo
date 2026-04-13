import { useEffect, useState } from 'react';
import { api } from '../services/api';
import SeverityBadge from '../components/SeverityBadge';

interface MapNode {
  id: string;
  type: string;
  label: string;
  risk_score?: number;
  risk_tier?: string;
  severity?: string;
  supplier_type?: string;
  region?: string;
  country_code?: string;
}

interface MapEdge {
  source: string;
  target: string;
  relationship: string;
}

const typeColors: Record<string, string> = {
  organization: 'bg-blue-100 border-blue-400 text-blue-900',
  supplier: 'bg-green-100 border-green-400 text-green-900',
  risk: 'bg-red-100 border-red-400 text-red-900',
};

export default function SupplyChainMapPage() {
  const [nodes, setNodes] = useState<MapNode[]>([]);
  const [edges, setEdges] = useState<MapEdge[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

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

  const suppliers = nodes.filter((n) => n.type === 'supplier');
  const risks = nodes.filter((n) => n.type === 'risk');
  const orgs = nodes.filter((n) => n.type === 'organization');

  if (loading) return <p className="text-sm text-gray-400">Loading supply chain map...</p>;
  if (error) return <p className="text-sm text-red-500">{error}</p>;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Supply Chain Map</h1>
        <p className="text-sm text-gray-500 mt-1">
          {nodes.length} nodes, {edges.length} connections
        </p>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 text-center">
          <p className="text-3xl font-bold text-blue-700">{orgs.length}</p>
          <p className="text-xs text-blue-600">Organizations</p>
        </div>
        <div className="bg-green-50 border border-green-200 rounded-xl p-4 text-center">
          <p className="text-3xl font-bold text-green-700">{suppliers.length}</p>
          <p className="text-xs text-green-600">Suppliers</p>
        </div>
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-center">
          <p className="text-3xl font-bold text-red-700">{risks.length}</p>
          <p className="text-xs text-red-600">Active Risks</p>
        </div>
      </div>

      {/* Network Graph (node list representation) */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Supply Chain Nodes</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {nodes.map((node) => (
            <div
              key={node.id}
              className={`border-2 rounded-lg p-3 ${typeColors[node.type] || 'bg-gray-100 border-gray-300 text-gray-900'}`}
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold uppercase opacity-60">{node.type}</span>
                {node.risk_tier && <SeverityBadge severity={node.risk_tier} />}
                {node.severity && <SeverityBadge severity={node.severity} />}
              </div>
              <p className="font-medium mt-1">{node.label}</p>
              {node.region && <p className="text-xs opacity-70">{node.country_code} — {node.region}</p>}
              {node.supplier_type && <p className="text-xs opacity-70 capitalize">{node.supplier_type.replace('_', ' ')}</p>}
              {node.risk_score != null && node.risk_score > 0 && (
                <div className="mt-2">
                  <div className="bg-white/50 rounded-full h-1.5">
                    <div
                      className={`rounded-full h-1.5 ${node.risk_score > 65 ? 'bg-red-500' : node.risk_score > 40 ? 'bg-yellow-500' : 'bg-green-500'}`}
                      style={{ width: `${node.risk_score}%` }}
                    />
                  </div>
                  <p className="text-xs mt-0.5">Risk: {node.risk_score.toFixed(0)}/100</p>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Connections */}
      {edges.length > 0 && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Connections ({edges.length})</h2>
          <div className="space-y-2">
            {edges.map((edge, i) => {
              const sourceNode = nodes.find((n) => n.id === edge.source);
              const targetNode = nodes.find((n) => n.id === edge.target);
              return (
                <div key={i} className="flex items-center gap-2 text-sm text-gray-600">
                  <span className="font-medium text-gray-900">{sourceNode?.label || edge.source.slice(0, 8)}</span>
                  <span className="text-xs px-2 py-0.5 bg-gray-100 rounded">{edge.relationship}</span>
                  <span className="font-medium text-gray-900">{targetNode?.label || edge.target.slice(0, 8)}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
