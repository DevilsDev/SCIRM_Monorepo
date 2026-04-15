import { useEffect, useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { PlusIcon, PencilSquareIcon, TrashIcon, ArrowUpTrayIcon } from '@heroicons/react/24/outline';
import { api, Supplier } from '../services/api';
import RadarChart from '../components/d3/RadarChart';
import { Modal, ConfirmDialog } from '../components/ui';
import SupplierForm from '../components/forms/SupplierForm';
import CSVUpload from '../components/CSVUpload';
import { useToast } from '../components/Toast';

const tierColors: Record<string, string> = {
  low: 'bg-green-100 text-green-800',
  medium: 'bg-yellow-100 text-yellow-800',
  high: 'bg-orange-100 text-orange-800',
  critical: 'bg-red-100 text-red-800',
};

function RiskScoreBar({ score }: { score: number }) {
  const color = score < 40 ? 'bg-green-500' : score < 65 ? 'bg-yellow-500' : score < 80 ? 'bg-orange-500' : 'bg-red-500';
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 bg-gray-200 rounded-full h-2 max-w-[120px]">
        <div className={`${color} rounded-full h-2`} style={{ width: `${score}%` }} />
      </div>
      <span className="text-sm font-medium text-gray-700 dark:text-gray-300">{score.toFixed(0)}</span>
    </div>
  );
}

interface DimensionScore {
  dimension: string;
  label: string;
  score: number;
  confidence: number;
  trend: string;
  reasoning: string;
}

export default function SuppliersPage() {
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [tierFilter, setTierFilter] = useState('');
  const [selectedSupplier, setSelectedSupplier] = useState<Supplier | null>(null);
  const [radarData, setRadarData] = useState<DimensionScore[]>([]);
  const [scoringLoading, setScoringLoading] = useState(false);
  const { t } = useTranslation();
  const { addToast } = useToast();

  // CRUD state
  const [showAddModal, setShowAddModal] = useState(false);
  const [editingSupplier, setEditingSupplier] = useState<Supplier | null>(null);
  const [deletingSupplier, setDeletingSupplier] = useState<Supplier | null>(null);
  const [showImportModal, setShowImportModal] = useState(false);

  const fetchSuppliers = useCallback(() => {
    setLoading(true);
    api
      .getSuppliers({ risk_tier: tierFilter || undefined })
      .then((data) => setSuppliers(data.suppliers || []))
      .catch((err) => setError(err.message || 'Failed to load suppliers'))
      .finally(() => setLoading(false));
  }, [tierFilter]);

  useEffect(() => { fetchSuppliers(); }, [fetchSuppliers]);

  const handleSupplierClick = async (supplier: Supplier) => {
    setSelectedSupplier(supplier);
    setScoringLoading(true);
    setRadarData([]);
    try {
      const result = await api.scoreSupplierRisk(supplier.name, {
        country_code: supplier.country_code,
        region: supplier.region,
        risk_score: supplier.risk_score,
        supplier_type: supplier.supplier_type,
      });
      setRadarData(result.dimension_scores || []);
    } catch {
      setRadarData([]);
    } finally {
      setScoringLoading(false);
    }
  };

  const handleCreateSupplier = async (values: any) => {
    await api.createSupplier(values);
    addToast('success', t('suppliers.created', 'Supplier created'), t('suppliers.createdDesc', '{{name}} has been added', { name: values.name }));
    setShowAddModal(false);
    fetchSuppliers();
  };

  const handleUpdateSupplier = async (values: any) => {
    if (!editingSupplier) return;
    await api.updateSupplier(editingSupplier.id, values);
    addToast('success', t('suppliers.updated', 'Supplier updated'), t('suppliers.updatedDesc', '{{name}} has been updated', { name: values.name }));
    setEditingSupplier(null);
    fetchSuppliers();
  };

  const handleDeleteSupplier = async () => {
    if (!deletingSupplier) return;
    try {
      await api.deleteSupplier(deletingSupplier.id);
      addToast('success', t('suppliers.deleted', 'Supplier deleted'), t('suppliers.deletedDesc', '{{name}} has been removed', { name: deletingSupplier.name }));
      setDeletingSupplier(null);
      fetchSuppliers();
    } catch {
      addToast('error', t('common.error', 'Error'), t('suppliers.deleteFailed', 'Failed to delete supplier'));
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{t('suppliers.title', 'Suppliers')}</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">{t('suppliers.tracked', '{{count}} suppliers tracked', { count: suppliers.length })} — {t('suppliers.clickForProfile', 'click a supplier for 7-dimension risk profile')}</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setShowAddModal(true)}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors"
          >
            <PlusIcon className="h-4 w-4" />
            {t('suppliers.addSupplier', 'Add Supplier')}
          </button>
          <button
            onClick={() => setShowImportModal(true)}
            className="flex items-center gap-2 px-4 py-2 bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg text-sm font-medium hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors"
          >
            <ArrowUpTrayIcon className="h-4 w-4" />
            {t('csv.import', 'Import CSV')}
          </button>
        </div>
      </div>

      <div className="flex gap-3">
        <select
          value={tierFilter}
          onChange={(e) => setTierFilter(e.target.value)}
          className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm bg-white dark:bg-gray-800 focus:ring-2 focus:ring-blue-500 outline-none"
        >
          <option value="">{t('suppliers.allTiers', 'All Risk Tiers')}</option>
          <option value="low">{t('risks.low', 'Low')}</option>
          <option value="medium">{t('risks.medium', 'Medium')}</option>
          <option value="high">{t('risks.high', 'High')}</option>
        </select>
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 overflow-hidden">
        {loading ? (
          <p className="p-6 text-sm text-gray-400">{t('suppliers.loading', 'Loading suppliers...')}</p>
        ) : error ? (
          <p className="p-6 text-sm text-red-500">{error}</p>
        ) : suppliers.length === 0 ? (
          <div className="p-12 text-center">
            <p className="text-sm text-gray-400 mb-4">{t('suppliers.noSuppliers', 'No suppliers found.')}</p>
            <button
              onClick={() => setShowAddModal(true)}
              className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700"
            >
              <PlusIcon className="h-4 w-4" />
              {t('suppliers.addFirst', 'Add your first supplier')}
            </button>
          </div>
        ) : (
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50 dark:bg-gray-900">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">{t('suppliers.colName', 'Name')}</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">{t('suppliers.colCode', 'Code')}</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">{t('suppliers.colType', 'Type')}</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">{t('suppliers.colRegion', 'Region')}</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">{t('suppliers.colRiskScore', 'Risk Score')}</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">{t('suppliers.colRiskTier', 'Risk Tier')}</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">{t('suppliers.colActions', 'Actions')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {suppliers.map((s) => (
                <tr
                  key={s.id}
                  className="hover:bg-blue-50 dark:hover:bg-gray-700/50 cursor-pointer transition-colors"
                  onClick={() => handleSupplierClick(s)}
                >
                  <td className="px-6 py-4 text-sm font-medium text-blue-600">{s.name}</td>
                  <td className="px-6 py-4 text-sm text-gray-500 dark:text-gray-400 font-mono">{s.supplier_code}</td>
                  <td className="px-6 py-4 text-sm text-gray-500 dark:text-gray-400 capitalize">{s.supplier_type.replace('_', ' ')}</td>
                  <td className="px-6 py-4 text-sm text-gray-500 dark:text-gray-400">{s.country_code} {s.region}</td>
                  <td className="px-6 py-4"><RiskScoreBar score={s.risk_score} /></td>
                  <td className="px-6 py-4">
                    <span className={`inline-flex px-2.5 py-0.5 rounded-full text-xs font-medium ${tierColors[s.risk_tier] || 'bg-gray-100 dark:bg-gray-700 text-gray-800'}`}>
                      {t(`common.severity${s.risk_tier?.charAt(0).toUpperCase()}${s.risk_tier?.slice(1)}` as any, s.risk_tier)}
                    </span>
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex gap-2" onClick={(e) => e.stopPropagation()}>
                      <button onClick={() => setEditingSupplier(s)} className="p-1.5 text-gray-400 hover:text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-900/30 rounded-lg transition-colors" title={t('common.edit', 'Edit')}>
                        <PencilSquareIcon className="h-4 w-4" />
                      </button>
                      <button onClick={() => setDeletingSupplier(s)} className="p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/30 rounded-lg transition-colors" title={t('common.delete', 'Delete')}>
                        <TrashIcon className="h-4 w-4" />
                      </button>
                      <Link to="/simulator" className="text-[10px] text-blue-600 hover:text-blue-800 font-medium leading-8">{t('suppliers.simulate', 'Simulate')}</Link>
                      <Link to="/procurement" className="text-[10px] text-purple-600 hover:text-purple-800 font-medium leading-8">{t('suppliers.alternatives', 'Alternatives')}</Link>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Add Supplier Modal */}
      <Modal
        open={showAddModal}
        onClose={() => setShowAddModal(false)}
        title={t('suppliers.addSupplier', 'Add Supplier')}
        description={t('suppliers.addDesc', 'Add a new supplier to your supply chain network')}
        size="lg"
      >
        <SupplierForm
          onSubmit={handleCreateSupplier}
          onCancel={() => setShowAddModal(false)}
          submitLabel={t('suppliers.addSupplier', 'Add Supplier')}
        />
      </Modal>

      {/* Edit Supplier Modal */}
      <Modal
        open={!!editingSupplier}
        onClose={() => setEditingSupplier(null)}
        title={t('suppliers.editSupplier', 'Edit Supplier')}
        description={editingSupplier?.name}
        size="lg"
      >
        {editingSupplier && (
          <SupplierForm
            initialValues={editingSupplier}
            onSubmit={handleUpdateSupplier}
            onCancel={() => setEditingSupplier(null)}
            submitLabel={t('suppliers.saveChanges', 'Save Changes')}
          />
        )}
      </Modal>

      {/* Delete Confirmation */}
      <ConfirmDialog
        open={!!deletingSupplier}
        onClose={() => setDeletingSupplier(null)}
        onConfirm={handleDeleteSupplier}
        title={t('suppliers.deleteTitle', 'Delete Supplier')}
        message={t('suppliers.deleteMessage', 'Are you sure you want to delete "{{name}}"? This action cannot be undone.', { name: deletingSupplier?.name })}
        confirmLabel={t('common.delete', 'Delete')}
        variant="danger"
      />

      {/* 7-Dimension Risk Profile Modal */}
      <Modal
        open={!!selectedSupplier}
        onClose={() => setSelectedSupplier(null)}
        title={selectedSupplier?.name}
        description={selectedSupplier ? `${t('suppliers.riskProfile', '7-Dimension Risk Profile')} — ${selectedSupplier.country_code} ${selectedSupplier.region}` : ''}
      >
        {scoringLoading ? (
          <div className="flex items-center justify-center h-64">
            <p className="text-sm text-gray-400">{t('suppliers.scoring', 'Scoring across 7 dimensions...')}</p>
          </div>
        ) : radarData.length > 0 ? (
          <>
            <div className="flex justify-center">
              <RadarChart data={radarData} size={280} />
            </div>
            <div className="mt-4 grid grid-cols-2 gap-2">
              {radarData.map((d) => (
                <div key={d.dimension} className="flex items-center justify-between px-3 py-2 bg-gray-50 dark:bg-gray-900 rounded-lg">
                  <span className="text-xs font-medium text-gray-700 dark:text-gray-300">{d.label}</span>
                  <div className="flex items-center gap-2">
                    <span className={`text-xs font-bold ${d.score > 65 ? 'text-red-600' : d.score > 40 ? 'text-yellow-600' : 'text-green-600'}`}>
                      {d.score.toFixed(0)}
                    </span>
                    <span className="text-[9px] text-gray-400 capitalize">{d.trend}</span>
                  </div>
                </div>
              ))}
            </div>
          </>
        ) : (
          <p className="text-sm text-gray-400 text-center py-8">{t('common.noData', 'No data available')}</p>
        )}
      </Modal>

      {/* CSV Import Modal */}
      <Modal open={showImportModal} onClose={() => setShowImportModal(false)} title={t('csv.importSuppliers', 'Import Suppliers')} description={t('csv.importDesc', 'Upload a CSV file to bulk import suppliers')} size="lg">
        <CSVUpload
          expectedColumns={['name', 'supplier_code', 'supplier_type', 'country_code', 'region']}
          entityLabel={t('suppliers.title', 'suppliers')}
          onUpload={async (rows) => {
            for (const row of rows) {
              try {
                await api.createSupplier(row);
              } catch { /* skip failed rows */ }
            }
            addToast('success', t('csv.importSuccess', '{{count}} suppliers imported', { count: rows.length }));
            setShowImportModal(false);
            fetchSuppliers();
          }}
        />
      </Modal>
    </div>
  );
}
