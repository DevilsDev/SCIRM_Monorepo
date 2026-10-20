import { useEffect, useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { PlusIcon, PencilSquareIcon, TrashIcon, ArrowUpTrayIcon } from '@heroicons/react/24/outline';
import { api, Supplier, SupplierSignalSummary } from '../services/api';
import { Modal, ConfirmDialog } from '../components/ui';
import SupplierForm from '../components/forms/SupplierForm';
import CSVUpload from '../components/CSVUpload';
import { useToast } from '../components/Toast';
import SupplierSignals from '../components/SupplierSignals';
import SupplierAsk from '../components/SupplierAsk';
import SupplierSites from '../components/SupplierSites';
import SeverityBadge from '../components/SeverityBadge';
import { useFeatures } from '../services/features';
import { formatSpend } from '../components/SapSpendImport';

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

export default function SuppliersPage() {
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [tierFilter, setTierFilter] = useState('');
  const [sortBy, setSortBy] = useState<'default' | 'spend' | 'events'>('default');
  const [selectedSupplier, setSelectedSupplier] = useState<Supplier | null>(null);
  // Bumped when sites change, so the public-records panel re-matches exposure.
  const [signalsVersion, setSignalsVersion] = useState(0);
  const [signalSummary, setSignalSummary] = useState<Record<string, SupplierSignalSummary> | null>(null);
  const { t } = useTranslation();
  const { samplePages } = useFeatures();
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

  // Public-record counts per supplier; the column shows a dash if matching is unavailable.
  useEffect(() => {
    api.getSignalsOverview(365)
      .then((data) => setSignalSummary(Object.fromEntries(data.suppliers.map((r) => [r.supplier_id, r]))))
      .catch(() => setSignalSummary(null));
  }, [suppliers]);

  // The panel shows evidence (public records, cited answers) only. A rule-based
  // "risk profile" was removed: it produced the same numbers for every unassessed supplier.
  const handleSupplierClick = (supplier: Supplier) => setSelectedSupplier(supplier);

  const displayed = sortBy === 'default' ? suppliers : [...suppliers].sort((a, b) => sortBy === 'spend'
    ? (a.spend_rank ?? Infinity) - (b.spend_rank ?? Infinity)
    : (signalSummary?.[b.id]?.incidents ?? 0) - (signalSummary?.[a.id]?.incidents ?? 0));

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
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">{t('suppliers.tracked', '{{count}} suppliers tracked', { count: suppliers.length })} — {t('suppliers.clickForRecords', 'click a supplier for its public records')}</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setShowAddModal(true)}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors"
          >
            <PlusIcon className="h-4 w-4" />
            {t('suppliers.addSupplier', 'Add Supplier')}
          </button>
          <Link
            to="/scan"
            className="flex items-center gap-2 px-4 py-2 bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg text-sm font-medium hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors"
          >
            {t('scan.open', 'Scan a supplier list')}
          </Link>
          <Link
            to="/suppliers/import/sap"
            className="flex items-center gap-2 px-4 py-2 bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg text-sm font-medium hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors"
          >
            {t('sap.open', 'Import from SAP')}
          </Link>
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
        {(tierFilter || suppliers.some((x) => x.risk_tier)) && (
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
        )}
        <select
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value as 'default' | 'spend' | 'events')}
          aria-label={t('suppliers.sortBy', 'Sort suppliers')}
          className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm bg-white dark:bg-gray-800 focus:ring-2 focus:ring-blue-500 outline-none"
        >
          <option value="default">{t('suppliers.sortDefault', 'Sort: as listed')}</option>
          <option value="spend">{t('suppliers.sortSpend', 'Sort: largest spend')}</option>
          <option value="events">{t('suppliers.sortEvents', 'Sort: most public events')}</option>
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
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase" title={t('suppliers.colPublicRecordsHint', 'FDA events naming this supplier in the last 12 months (a recall covering several products counts once)')}>{t('suppliers.colPublicRecords', 'Public Events (12 mo)')}</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase" title={t('suppliers.colSpendHint', 'Purchase-order spend in the last 12 months, from the SAP spend import; share of the total in the main currency')}>{t('suppliers.colSpend', 'Spend (12 mo)')}</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">{t('suppliers.colActions', 'Actions')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {displayed.map((s) => (
                <tr
                  key={s.id}
                  className="hover:bg-blue-50 dark:hover:bg-gray-700/50 cursor-pointer transition-colors"
                  onClick={() => handleSupplierClick(s)}
                >
                  <td className="px-6 py-4 text-sm font-medium text-blue-600">
                    {s.name}
                    {s.demo_note && (
                      <span title={s.demo_note} className="ml-2 inline-flex px-1.5 py-0.5 rounded text-[9px] font-bold uppercase bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-300">
                        {t('suppliers.demo', 'Demo')}
                      </span>
                    )}
                    {!s.is_active && (
                      <span className="ml-2 inline-flex px-1.5 py-0.5 rounded text-[9px] font-bold uppercase bg-gray-200 dark:bg-gray-700 text-gray-600 dark:text-gray-300">
                        {t('suppliers.inactive', 'Inactive')}
                      </span>
                    )}
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-500 dark:text-gray-400 font-mono">{s.supplier_code}</td>
                  <td className="px-6 py-4 text-sm text-gray-500 dark:text-gray-400 capitalize">{s.supplier_type.replace('_', ' ')}</td>
                  <td className="px-6 py-4 text-sm text-gray-500 dark:text-gray-400">{[s.country_code, s.region].filter(Boolean).join(' ')}</td>
                  {s.demo_note || s.risk_score === null ? (
                    // Never show a rating nobody made: demo suppliers and unassessed ones are not scored.
                    <td colSpan={2} className="px-6 py-4 text-xs text-gray-400" title={s.demo_note}>
                      {s.demo_note
                        ? t('suppliers.notScored', 'Not scored (demo supplier); see public records')
                        : t('suppliers.notAssessed', 'Not assessed; see public records')}
                    </td>
                  ) : (
                    <>
                      <td className="px-6 py-4"><RiskScoreBar score={s.risk_score} /></td>
                      <td className="px-6 py-4">
                        <span className={`inline-flex px-2.5 py-0.5 rounded-full text-xs font-medium ${(s.risk_tier && tierColors[s.risk_tier]) || 'bg-gray-100 dark:bg-gray-700 text-gray-800'}`}>
                          {t(`common.severity${s.risk_tier?.charAt(0).toUpperCase()}${s.risk_tier?.slice(1)}` as any, s.risk_tier ?? '')}
                        </span>
                      </td>
                    </>
                  )}
                  <td className="px-6 py-4 text-sm text-gray-700 dark:text-gray-300 whitespace-nowrap"
                    title={s.spend_period ? t('suppliers.spendPeriod', '{{from}} to {{to}}', s.spend_period) : t('suppliers.noSpend', 'No purchase-order spend imported')}>
                    {s.spend_main_currency && s.spend_12m ? (
                      <>
                        {formatSpend(s.spend_12m[s.spend_main_currency] ?? '0', s.spend_main_currency)}
                        {s.spend_share != null && <span className="ml-1 text-xs text-gray-400">{(s.spend_share * 100).toFixed(1)}%</span>}
                        {Object.keys(s.spend_12m).filter((c) => c !== s.spend_main_currency).map((c) => (
                          <span key={c} className="block text-xs text-gray-400">+ {formatSpend(s.spend_12m![c], c)}</span>
                        ))}
                      </>
                    ) : <span className="text-gray-300">–</span>}
                  </td>
                  <td className="px-6 py-4">
                    {signalSummary?.[s.id]?.incidents ? (
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-gray-700 dark:text-gray-300">{signalSummary[s.id].incidents}</span>
                        {signalSummary[s.id].worst_incident_severity && <SeverityBadge severity={signalSummary[s.id].worst_incident_severity!} />}
                        {signalSummary[s.id].watch && (
                          <span
                            className="inline-flex px-1.5 py-0.5 rounded text-[9px] font-bold uppercase bg-amber-100 text-amber-800"
                            title={t('suppliers.watchHint', 'Recent FDA recalls at a level that, in back-tests on 2023-2026 data, came 30+ days before about 4 in 10 serious (Class I) recalls at firms with FDA history. Most watched suppliers do not go on to have one.')}
                          >
                            {t('suppliers.watch', 'Watch')}
                          </span>
                        )}
                      </div>
                    ) : (
                      <span className="text-sm text-gray-400">{signalSummary ? '0' : '-'}</span>
                    )}
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex gap-2" onClick={(e) => e.stopPropagation()}>
                      <button onClick={() => setEditingSupplier(s)} className="p-1.5 text-gray-400 hover:text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-900/30 rounded-lg transition-colors" title={t('common.edit', 'Edit')}>
                        <PencilSquareIcon className="h-4 w-4" />
                      </button>
                      <button onClick={() => setDeletingSupplier(s)} className="p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/30 rounded-lg transition-colors" title={t('common.delete', 'Delete')}>
                        <TrashIcon className="h-4 w-4" />
                      </button>
                      {samplePages && (
                        <>
                          <Link to="/simulator" className="text-[10px] text-blue-600 hover:text-blue-800 font-medium leading-8">{t('suppliers.simulate', 'Simulate')}</Link>
                          <Link to="/procurement" className="text-[10px] text-purple-600 hover:text-purple-800 font-medium leading-8">{t('suppliers.alternatives', 'Alternatives')}</Link>
                        </>
                      )}
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
        description={selectedSupplier ? [selectedSupplier.country_code, selectedSupplier.region].filter(Boolean).join(' · ') : ''}
      >
        {selectedSupplier?.demo_note && <p className="text-xs text-gray-400 pb-2">{selectedSupplier.demo_note}</p>}
        {selectedSupplier && (
          <div className="mt-2">
            <h2 className="text-sm font-semibold text-gray-900 dark:text-white mb-2">{t('ask.title', 'Ask about this supplier')}</h2>
            <SupplierAsk supplierId={selectedSupplier.id} />
            <h2 className="text-sm font-semibold text-gray-900 dark:text-white mt-6 mb-2">{t('sites.title', 'Sites')}</h2>
            <SupplierSites supplier={selectedSupplier} onChange={(updated) => {
              setSelectedSupplier(updated);
              setSuppliers((list) => list.map((x) => (x.id === updated.id ? updated : x)));
              setSignalsVersion((v) => v + 1);
            }} />
            <h2 className="text-sm font-semibold text-gray-900 dark:text-white mt-6 mb-2">{t('signals.title', 'Public records')}</h2>
            <SupplierSignals key={`${selectedSupplier.id}-${signalsVersion}`} supplierId={selectedSupplier.id} />
          </div>
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
