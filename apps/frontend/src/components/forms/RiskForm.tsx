import { useTranslation } from 'react-i18next';
import { useForm, validators } from '../../hooks/useForm';
import { FormField, TextInput, Select, TextArea, TagInput } from '../ui';

interface RiskFormProps {
  initialValues?: any;
  onSubmit: (values: any) => Promise<void>;
  onCancel: () => void;
  submitLabel?: string;
}

const SEVERITIES = [
  { value: 'low', label: 'Low' },
  { value: 'medium', label: 'Medium' },
  { value: 'high', label: 'High' },
  { value: 'critical', label: 'Critical' },
];

const CATEGORIES = [
  { value: 'supplier', label: 'Supplier' },
  { value: 'logistics', label: 'Logistics' },
  { value: 'regulatory', label: 'Regulatory' },
  { value: 'financial', label: 'Financial' },
  { value: 'quality', label: 'Quality' },
  { value: 'geopolitical', label: 'Geopolitical' },
  { value: 'environmental', label: 'Environmental' },
  { value: 'cyber', label: 'Cybersecurity' },
];

export default function RiskForm({ initialValues, onSubmit, onCancel, submitLabel }: RiskFormProps) {
  const { t } = useTranslation();

  const { values, errors, touched, isSubmitting, handleChange, handleBlur, handleSubmit, setFieldValue } = useForm({
    initialValues: {
      title: initialValues?.title || '',
      description: initialValues?.description || '',
      severity: initialValues?.severity || 'medium',
      probability: initialValues?.probability ? String(initialValues.probability * 100) : '50',
      impact_score: initialValues?.impact_score ? String(initialValues.impact_score) : '5.0',
      risk_category: initialValues?.risk_category || '',
      affected_entities: initialValues?.affected_entities || [],
    },
    validators: {
      title: [validators.required(t('forms.required', 'This field is required'))],
      severity: [validators.required(t('forms.required', 'This field is required'))],
      risk_category: [validators.required(t('forms.selectType', 'Please select a category'))],
    },
    onSubmit: async (vals) => {
      await onSubmit({
        ...vals,
        probability: Number(vals.probability) / 100,
        impact_score: Number(vals.impact_score),
      });
    },
  });

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <FormField label={t('risks.formTitle', 'Risk Title')} error={touched.title ? errors.title : undefined} required>
        <TextInput name="title" value={values.title} onChange={handleChange} onBlur={handleBlur} error={!!errors.title && !!touched.title} placeholder="e.g. Single-source dependency on Supplier X" />
      </FormField>

      <FormField label={t('risks.formDescription', 'Description')}>
        <TextArea name="description" value={values.description} onChange={handleChange} placeholder={t('risks.descPlaceholder', 'Describe the risk, its root cause, and potential impact...')} rows={3} showCount maxLength={1000} />
      </FormField>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <FormField label={t('risks.colSeverity', 'Severity')} error={touched.severity ? errors.severity : undefined} required>
          <Select name="severity" value={values.severity} onChange={handleChange} options={SEVERITIES} />
        </FormField>

        <FormField label={t('risks.colProbability', 'Probability (%)')}>
          <TextInput name="probability" type="number" value={values.probability} onChange={handleChange} min={0} max={100} step={5} />
        </FormField>

        <FormField label={t('risks.impactScore', 'Impact Score (1-10)')}>
          <TextInput name="impact_score" type="number" value={values.impact_score} onChange={handleChange} min={1} max={10} step={0.5} />
        </FormField>
      </div>

      <FormField label={t('risks.colCategory', 'Category')} error={touched.risk_category ? errors.risk_category : undefined} required>
        <Select name="risk_category" value={values.risk_category} onChange={handleChange} onBlur={handleBlur} error={!!errors.risk_category && !!touched.risk_category} options={CATEGORIES} placeholder={t('forms.selectPlaceholder', 'Select...')} />
      </FormField>

      <FormField label={t('risks.affectedEntities', 'Affected Entities')}>
        <TagInput value={values.affected_entities} onChange={(tags) => setFieldValue('affected_entities', tags)} placeholder={t('risks.entitiesPlaceholder', 'Type entity name and press Enter...')} />
      </FormField>

      <div className="flex justify-end gap-3 pt-4 border-t border-gray-200 dark:border-gray-700">
        <button type="button" onClick={onCancel} disabled={isSubmitting} className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors">
          {t('common.cancel', 'Cancel')}
        </button>
        <button type="submit" disabled={isSubmitting} className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50">
          {isSubmitting ? t('common.loading', 'Loading...') : submitLabel || t('common.save', 'Save')}
        </button>
      </div>
    </form>
  );
}
