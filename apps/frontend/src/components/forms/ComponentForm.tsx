import { useTranslation } from 'react-i18next';
import { useForm, validators } from '../../hooks/useForm';
import { FormField, TextInput, Select, MultiSelect } from '../ui';

interface ComponentFormProps {
  initialValues?: any;
  supplierOptions?: { value: string; label: string }[];
  onSubmit: (values: any) => Promise<void>;
  onCancel: () => void;
  submitLabel?: string;
}

const CRITICALITIES = [
  { value: 'low', label: 'Low' },
  { value: 'medium', label: 'Medium' },
  { value: 'high', label: 'High' },
  { value: 'critical', label: 'Critical' },
];

const CATEGORIES = [
  { value: 'active_ingredient', label: 'Active Ingredient' },
  { value: 'excipient', label: 'Excipient' },
  { value: 'packaging', label: 'Packaging' },
  { value: 'monitoring', label: 'Monitoring' },
  { value: 'material', label: 'Material' },
  { value: 'electronic', label: 'Electronic' },
  { value: 'mechanical', label: 'Mechanical' },
];

export default function ComponentForm({ initialValues, supplierOptions = [], onSubmit, onCancel, submitLabel }: ComponentFormProps) {
  const { t } = useTranslation();

  const { values, errors, touched, isSubmitting, handleChange, handleBlur, handleSubmit, setFieldValue } = useForm({
    initialValues: {
      name: initialValues?.name || '',
      part_number: initialValues?.part_number || '',
      category: initialValues?.category || '',
      criticality: initialValues?.criticality || 'medium',
      quantity: initialValues?.quantity ? String(initialValues.quantity) : '1',
      suppliers: initialValues?.suppliers || [],
    },
    validators: {
      name: [validators.required(t('forms.required', 'This field is required'))],
      part_number: [validators.required(t('forms.required', 'This field is required')), validators.pattern(/^[A-Z0-9-]+$/i, t('forms.codeFormat', 'Use letters, numbers, and hyphens only'))],
      category: [validators.required(t('forms.selectType', 'Please select a category'))],
    },
    onSubmit: async (vals) => {
      await onSubmit({ ...vals, quantity: Number(vals.quantity) });
    },
  });

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <FormField label={t('components.formName', 'Component Name')} error={touched.name ? errors.name : undefined} required>
          <TextInput name="name" value={values.name} onChange={handleChange} onBlur={handleBlur} error={!!errors.name && !!touched.name} placeholder="e.g. API Compound X" />
        </FormField>

        <FormField label={t('components.formPartNumber', 'Part Number')} error={touched.part_number ? errors.part_number : undefined} required>
          <TextInput name="part_number" value={values.part_number} onChange={handleChange} onBlur={handleBlur} error={!!errors.part_number && !!touched.part_number} placeholder="e.g. API-X-500" />
        </FormField>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <FormField label={t('components.colCategory', 'Category')} error={touched.category ? errors.category : undefined} required>
          <Select name="category" value={values.category} onChange={handleChange} onBlur={handleBlur} error={!!errors.category && !!touched.category} options={CATEGORIES} placeholder={t('forms.selectPlaceholder', 'Select...')} />
        </FormField>

        <FormField label={t('components.colCriticality', 'Criticality')}>
          <Select name="criticality" value={values.criticality} onChange={handleChange} options={CRITICALITIES} />
        </FormField>

        <FormField label={t('components.colQuantity', 'Quantity')}>
          <TextInput name="quantity" type="number" value={values.quantity} onChange={handleChange} min={1} />
        </FormField>
      </div>

      {supplierOptions.length > 0 && (
        <FormField label={t('components.colSuppliers', 'Linked Suppliers')}>
          <MultiSelect options={supplierOptions} value={values.suppliers} onChange={(v) => setFieldValue('suppliers', v)} placeholder={t('components.selectSuppliers', 'Select suppliers...')} />
        </FormField>
      )}

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
