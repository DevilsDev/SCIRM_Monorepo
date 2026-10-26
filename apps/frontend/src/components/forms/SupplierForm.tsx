import { useTranslation } from 'react-i18next';
import { useForm, validators } from '../../hooks/useForm';
import { FormField, TextInput, Select } from '../ui';
import Toggle from '../Toggle';
import { Supplier } from '../../services/api';

interface SupplierFormProps {
  initialValues?: Partial<Supplier>;
  onSubmit: (values: any) => Promise<void>;
  onCancel: () => void;
  submitLabel?: string;
}

const SUPPLIER_TYPES = [
  { value: 'api_manufacturer', label: 'API Manufacturer' },
  { value: 'excipient', label: 'Excipient Supplier' },
  { value: 'packaging', label: 'Packaging' },
  { value: 'sensor_components', label: 'Sensor Components' },
  { value: 'biocompatible_materials', label: 'Biocompatible Materials' },
  { value: 'logistics', label: 'Logistics' },
  { value: 'general', label: 'General' },
];

const REGIONS = [
  { value: 'North America', label: 'North America' },
  { value: 'Europe', label: 'Europe' },
  { value: 'Asia Pacific', label: 'Asia Pacific' },
  { value: 'Latin America', label: 'Latin America' },
  { value: 'Middle East', label: 'Middle East' },
  { value: 'Africa', label: 'Africa' },
];

export default function SupplierForm({ initialValues, onSubmit, onCancel, submitLabel }: SupplierFormProps) {
  const { t } = useTranslation();

  const { values, errors, touched, isSubmitting, handleChange, handleBlur, handleSubmit, setFieldValue } = useForm({
    initialValues: {
      name: initialValues?.name || '',
      supplier_code: initialValues?.supplier_code || '',
      supplier_type: initialValues?.supplier_type || '',
      country_code: initialValues?.country_code || '',
      region: initialValues?.region || '',
      contact_name: initialValues?.contact_name || '',
      contact_email: initialValues?.contact_email || '',
      is_active: initialValues?.is_active ?? true,
    },
    validators: {
      name: [validators.required(t('forms.required', 'This field is required'))],
      supplier_code: [validators.required(t('forms.required', 'This field is required')), validators.pattern(/^[A-Z0-9-]+$/i, t('forms.codeFormat', 'Use letters, numbers, and hyphens only'))],
      supplier_type: [validators.required(t('forms.selectType', 'Please select a type'))],
      contact_email: [validators.email(t('forms.invalidEmail', 'Invalid email address'))],
    },
    onSubmit,
  });

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <FormField label={t('suppliers.formName', 'Supplier Name')} error={touched.name ? errors.name : undefined} required>
          <TextInput name="name" value={values.name} onChange={handleChange} onBlur={handleBlur} error={!!errors.name && !!touched.name} placeholder="e.g. Acme Corp" />
        </FormField>

        <FormField label={t('suppliers.formCode', 'Supplier Code')} error={touched.supplier_code ? errors.supplier_code : undefined} required>
          <TextInput name="supplier_code" value={values.supplier_code} onChange={handleChange} onBlur={handleBlur} error={!!errors.supplier_code && !!touched.supplier_code} placeholder="e.g. SUP-ACME" />
        </FormField>
      </div>

      <FormField label={t('suppliers.formType', 'Supplier Type')} error={touched.supplier_type ? errors.supplier_type : undefined} required>
        <Select name="supplier_type" value={values.supplier_type} onChange={handleChange} onBlur={handleBlur} error={!!errors.supplier_type && !!touched.supplier_type} options={SUPPLIER_TYPES} placeholder={t('forms.selectPlaceholder', 'Select...')} />
      </FormField>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <FormField label={t('suppliers.formCountry', 'Country Code')} hint="e.g. US, DE, CN">
          <TextInput name="country_code" value={values.country_code} onChange={handleChange} placeholder="US" maxLength={3} />
        </FormField>

        <FormField label={t('suppliers.formRegion', 'Region')}>
          <Select name="region" value={values.region} onChange={handleChange} options={REGIONS} placeholder={t('forms.selectPlaceholder', 'Select...')} />
        </FormField>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <FormField label={t('suppliers.formContactName', 'Contact Name')}>
          <TextInput name="contact_name" value={values.contact_name} onChange={handleChange} placeholder="John Doe" />
        </FormField>

        <FormField label={t('suppliers.formContactEmail', 'Contact Email')} error={touched.contact_email ? errors.contact_email : undefined}>
          <TextInput name="contact_email" type="email" value={values.contact_email} onChange={handleChange} onBlur={handleBlur} error={!!errors.contact_email && !!touched.contact_email} placeholder="john@acme.com" />
        </FormField>
      </div>

      <div className="pt-2">
        <Toggle
          enabled={values.is_active}
          onChange={(v) => setFieldValue('is_active', v)}
          label={t('suppliers.formActive', 'Active Supplier')}
          description={t('suppliers.formActiveDesc', 'Inactive suppliers are excluded from risk assessments')}
        />
      </div>

      <div className="flex justify-end gap-3 pt-4 border-t border-gray-200 dark:border-gray-700">
        <button
          type="button"
          onClick={onCancel}
          disabled={isSubmitting}
          className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
        >
          {t('common.cancel', 'Cancel')}
        </button>
        <button
          type="submit"
          disabled={isSubmitting}
          className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50"
        >
          {isSubmitting ? t('common.loading', 'Loading...') : submitLabel || t('common.save', 'Save')}
        </button>
      </div>
    </form>
  );
}
