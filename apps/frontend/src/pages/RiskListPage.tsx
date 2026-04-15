import { useState, useCallback, useEffect } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { PlusIcon, PencilSquareIcon } from '@heroicons/react/24/outline';
import SeverityBadge from '../components/SeverityBadge';
import Pagination from '../components/Pagination';
import { Modal } from '../components/ui';
import RiskForm from '../components/forms/RiskForm';
import { useRisks } from '../hooks/useRisks';
import { api } from '../services/api';
import { useToast } from '../components/Toast';

const PAGE_SIZE = 20;

export default function RiskListPage() {
  const [searchParams] = useSearchParams();
  const initialSeverity = searchParams.get('severity') || '';

  const [currentPage, setCurrentPage] = useState(1);
  const [severityFilter, setSeverityFilter] = useState(initialSeverity);
  const [showAddModal, setShowAddModal] = useState(false);
  const [editingRisk, setEditingRisk] = useState<any>(null);
  const { t } = useTranslation();
  const { addToast } = useToast();

  const { risks, totalCount, loading, error, refetch } = useRisks({
    limit: PAGE_SIZE,
    offset: (currentPage - 1) * PAGE_SIZE,
    severity: severityFilter || undefined,
  });

  // Sync URL params to filter state
  useEffect(() => {
    const sev = searchParams.get('severity');
    if (sev && sev !== severityFilter) {
      setSeverityFilter(sev);
      setCurrentPage(1);
    }
  }, [searchParams]);

  const handleCreateRisk = async (values: any) => {
    await api.createRisk(values);
    addToast('success', t('risks.created', 'Risk created'), t('risks.createdDesc', 'Manual risk entry has been added'));
    setShowAddModal(false);
    refetch();
  };

  const handleUpdateRisk = async (values: any) => {
    if (!editingRisk) return;
    await api.updateRisk(editingRisk.id, values);
    addToast('success', t('risks.updated', 'Risk updated'));
    setEditingRisk(null);
    refetch();
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{t('risks.title', 'Risk Overview')}</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">{t('risks.tracked', '{{count}} risks tracked', { count: totalCount })}</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setShowAddModal(true)}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors"
          >
            <PlusIcon className="h-4 w-4" />
            {t('risks.addRisk', 'Add Risk')}
          </button>
          <Link
            to="/assessments/new"
            className="px-4 py-2 bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg text-sm font-medium hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors"
          >
            {t('nav.newAssessment', 'New Assessment')}
          </Link>
        </div>
      </div>

      {/* Filters */}
      <div className="flex gap-3">
        <select
          value={severityFilter}
          onChange={(e) => {
            setSeverityFilter(e.target.value);
            setCurrentPage(1);
          }}
          className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm bg-white dark:bg-gray-800 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
        >
          <option value="">{t('risks.allSeverities', 'All Severities')}</option>
          <option value="critical">{t('risks.critical', 'Critical')}</option>
          <option value="high">{t('risks.high', 'High')}</option>
          <option value="medium">{t('risks.medium', 'Medium')}</option>
          <option value="low">{t('risks.low', 'Low')}</option>
        </select>
      </div>

      {/* Table */}
      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 overflow-hidden">
        {loading ? (
          <p className="p-6 text-sm text-gray-400">{t('risks.loading', 'Loading risks...')}</p>
        ) : error ? (
          <p className="p-6 text-sm text-red-500">{error}</p>
        ) : risks.length === 0 ? (
          <div className="p-12 text-center">
            <p className="text-sm text-gray-400 mb-4">{t('risks.noRisks', 'No risks found.')}</p>
            <button
              onClick={() => setShowAddModal(true)}
              className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700"
            >
              <PlusIcon className="h-4 w-4" />
              {t('risks.addFirst', 'Add your first risk')}
            </button>
          </div>
        ) : (
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50 dark:bg-gray-900">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">{t('risks.colTitle', 'Title')}</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">{t('risks.colSeverity', 'Severity')}</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">{t('risks.colProbability', 'Probability')}</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">{t('risks.colImpact', 'Impact')}</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">{t('risks.colCategory', 'Category')}</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">{t('risks.colDetected', 'Detected')}</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">{t('suppliers.colActions', 'Actions')}</th>
              </tr>
            </thead>
            <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200">
              {risks.map((risk) => (
                <tr key={risk.id} className="hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors">
                  <td className="px-6 py-4">
                    <Link to={`/risks/${risk.id}`} className="text-sm font-medium text-blue-600 hover:text-blue-800">
                      {risk.title}
                    </Link>
                  </td>
                  <td className="px-6 py-4">
                    <SeverityBadge severity={risk.severity} />
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-500 dark:text-gray-400">
                    {(risk.probability * 100).toFixed(0)}%
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-500 dark:text-gray-400">
                    {risk.impact_score.toFixed(1)}
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-500 dark:text-gray-400 capitalize">
                    {risk.risk_category}
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-500 dark:text-gray-400">
                    {new Date(risk.detected_at).toLocaleDateString()}
                  </td>
                  <td className="px-6 py-4">
                    <button
                      onClick={() => setEditingRisk(risk)}
                      className="p-1.5 text-gray-400 hover:text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-900/30 rounded-lg transition-colors"
                      title={t('common.edit', 'Edit')}
                    >
                      <PencilSquareIcon className="h-4 w-4" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        <Pagination
          currentPage={currentPage}
          totalItems={totalCount}
          pageSize={PAGE_SIZE}
          onPageChange={setCurrentPage}
        />
      </div>

      {/* Add Risk Modal */}
      <Modal open={showAddModal} onClose={() => setShowAddModal(false)} title={t('risks.addRisk', 'Add Risk')} description={t('risks.addDesc', 'Manually add a risk to your supply chain risk register')} size="lg">
        <RiskForm onSubmit={handleCreateRisk} onCancel={() => setShowAddModal(false)} submitLabel={t('risks.addRisk', 'Add Risk')} />
      </Modal>

      {/* Edit Risk Modal */}
      <Modal open={!!editingRisk} onClose={() => setEditingRisk(null)} title={t('risks.editRisk', 'Edit Risk')} description={editingRisk?.title} size="lg">
        {editingRisk && (
          <RiskForm initialValues={editingRisk} onSubmit={handleUpdateRisk} onCancel={() => setEditingRisk(null)} submitLabel={t('common.save', 'Save')} />
        )}
      </Modal>
    </div>
  );
}
