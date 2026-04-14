import { useEffect, useState } from 'react';
import { api } from '../services/api';

const critColors: Record<string, string> = {
  critical: 'bg-red-100 text-red-800',
  high: 'bg-orange-100 text-orange-800',
  medium: 'bg-yellow-100 text-yellow-800',
  low: 'bg-green-100 text-green-800',
};

export default function ComponentsPage() {
  const [products, setProducts] = useState<any[]>([]);
  const [components, setComponents] = useState<any[]>([]);
  const [selectedProduct, setSelectedProduct] = useState<any>(null);
  const [bom, setBom] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([api.getProducts(), api.getComponents()])
      .then(([prodData, compData]) => {
        setProducts(prodData.products || []);
        setComponents(compData.components || []);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const handleProductClick = async (product: any) => {
    setSelectedProduct(product);
    try {
      const data = await api.getProductBom(product.id);
      setBom(data.bom || []);
    } catch { setBom([]); }
  };

  if (loading) return <p className="text-sm text-gray-400">Loading components...</p>;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Components & BOM</h1>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">{components.length} components across {products.length} products</p>
      </div>

      {/* Products */}
      <div>
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">Products</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {products.map((p) => (
            <div
              key={p.id}
              onClick={() => handleProductClick(p)}
              className={`bg-white dark:bg-gray-800 rounded-xl shadow-sm border p-5 cursor-pointer transition-all hover:shadow-md ${
                selectedProduct?.id === p.id ? 'border-blue-500 ring-2 ring-blue-100' : 'border-gray-200 dark:border-gray-700'
              }`}
            >
              <h3 className="text-sm font-semibold text-gray-900 dark:text-white">{p.name}</h3>
              <div className="grid grid-cols-3 gap-2 mt-3">
                <div className="text-center">
                  <p className="text-lg font-bold text-gray-900 dark:text-white">{p.component_count}</p>
                  <p className="text-[10px] text-gray-500 dark:text-gray-400">Components</p>
                </div>
                <div className="text-center">
                  <p className="text-lg font-bold text-red-600">{p.critical_components}</p>
                  <p className="text-[10px] text-gray-500 dark:text-gray-400">Critical</p>
                </div>
                <div className="text-center">
                  <p className="text-lg font-bold text-gray-900 dark:text-white">{p.max_component_risk}</p>
                  <p className="text-[10px] text-gray-500 dark:text-gray-400">Max Risk</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* BOM Detail */}
      {selectedProduct && (
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 overflow-hidden">
          <div className="px-6 py-4 bg-gray-50 dark:bg-gray-900 border-b">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">BOM: {selectedProduct.name}</h2>
          </div>
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50 dark:bg-gray-900">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Component</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Part #</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Category</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Criticality</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Quantity</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Risk</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Suppliers</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {bom.map((item: any) => (
                <tr key={item.id} className={item.is_critical ? 'bg-red-50/30' : ''}>
                  <td className="px-6 py-3 text-sm font-medium text-gray-900 dark:text-white">{item.name}</td>
                  <td className="px-6 py-3 text-sm text-gray-500 dark:text-gray-400 font-mono">{item.part_number}</td>
                  <td className="px-6 py-3 text-sm text-gray-500 dark:text-gray-400 capitalize">{item.category?.replace('_', ' ')}</td>
                  <td className="px-6 py-3">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium capitalize ${critColors[item.criticality] || 'bg-gray-100 dark:bg-gray-700'}`}>
                      {item.criticality}
                    </span>
                  </td>
                  <td className="px-6 py-3 text-sm text-gray-500 dark:text-gray-400">{item.quantity}</td>
                  <td className="px-6 py-3">
                    <span className={`text-sm font-bold ${item.risk_score > 60 ? 'text-red-600' : item.risk_score > 40 ? 'text-yellow-600' : 'text-green-600'}`}>
                      {item.risk_score}
                    </span>
                  </td>
                  <td className="px-6 py-3 text-xs text-gray-500 dark:text-gray-400">{(item.suppliers || []).join(', ')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Component Catalog */}
      <div>
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">Component Catalog</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
          {components.map((c: any) => (
            <div key={c.id} className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-4">
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-mono text-gray-400">{c.part_number}</span>
                <span className={`px-2 py-0.5 rounded-full text-[10px] font-medium capitalize ${critColors[c.criticality] || 'bg-gray-100 dark:bg-gray-700'}`}>
                  {c.criticality}
                </span>
              </div>
              <p className="text-sm font-medium text-gray-900 dark:text-white">{c.name}</p>
              <p className="text-xs text-gray-500 dark:text-gray-400 capitalize mt-1">{c.category?.replace('_', ' ')}</p>
              <div className="flex items-center justify-between mt-2">
                <span className="text-xs text-gray-400">{(c.suppliers || []).length} supplier(s)</span>
                <span className={`text-sm font-bold ${c.risk_score > 60 ? 'text-red-600' : c.risk_score > 40 ? 'text-yellow-600' : 'text-green-600'}`}>
                  {c.risk_score}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
