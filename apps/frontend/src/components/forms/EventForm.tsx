import { useTranslation } from 'react-i18next';
import { useForm, validators } from '../../hooks/useForm';
import { FormField, TextInput, Select, TextArea } from '../ui';

interface EventFormProps {
  onSubmit: (values: any) => Promise<void>;
  onCancel: () => void;
}

const EVENT_TYPES = [
  { value: 'natural_disaster', label: 'Natural Disaster' },
  { value: 'geopolitical', label: 'Geopolitical' },
  { value: 'supplier_failure', label: 'Supplier Failure' },
  { value: 'logistics', label: 'Logistics Disruption' },
  { value: 'cyber_attack', label: 'Cyber Attack' },
  { value: 'regulatory', label: 'Regulatory Change' },
  { value: 'financial', label: 'Financial' },
];

const SEVERITIES = [
  { value: 'low', label: 'Low' },
  { value: 'medium', label: 'Medium' },
  { value: 'high', label: 'High' },
  { value: 'critical', label: 'Critical' },
];

export default function EventForm({ onSubmit, onCancel }: EventFormProps) {
  const { t } = useTranslation();

  const { values, errors, touched, isSubmitting, handleChange, handleBlur, handleSubmit } = useForm({
    initialValues: {
      title: '',
      event_type: '',
      severity: 'medium',
      affected_region: '',
      description: '',
    },
    validators: {
      title: [validators.required(t('forms.required', 'This field is required'))],
      event_type: [validators.required(t('forms.selectType', 'Please select a type'))],
      severity: [validators.required(t('forms.required', 'This field is required'))],
    },
    onSubmit: async (vals) => {
      await onSubmit({
        ...vals,
        affected_supplier_ids: [],
      });
    },
  });

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <FormField label={t('events.formTitle', 'Event Title')} error={touched.title ? errors.title : undefined} required>
        <TextInput name="title" value={values.title} onChange={handleChange} onBlur={handleBlur} error={!!errors.title && !!touched.title} placeholder="e.g. Port Congestion in Shanghai" />
      </FormField>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <FormField label={t('events.formType', 'Event Type')} error={touched.event_type ? errors.event_type : undefined} required>
          <Select name="event_type" value={values.event_type} onChange={handleChange} onBlur={handleBlur} error={!!errors.event_type && !!touched.event_type} options={EVENT_TYPES} placeholder={t('forms.selectPlaceholder', 'Select...')} />
        </FormField>

        <FormField label={t('events.formSeverity', 'Severity')} error={touched.severity ? errors.severity : undefined} required>
          <Select name="severity" value={values.severity} onChange={handleChange} options={SEVERITIES} />
        </FormField>
      </div>

      <FormField label={t('events.formRegion', 'Affected Region')}>
        <TextInput name="affected_region" value={values.affected_region} onChange={handleChange} placeholder="e.g. Asia Pacific" />
      </FormField>

      <FormField label={t('events.formDescription', 'Description')}>
        <TextArea name="description" value={values.description} onChange={handleChange} placeholder={t('events.descPlaceholder', 'Describe the event and its expected impact...')} rows={4} showCount maxLength={1000} />
      </FormField>

      <div className="flex justify-end gap-3 pt-4 border-t border-gray-200 dark:border-gray-700">
        <button type="button" onClick={onCancel} disabled={isSubmitting} className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors">
          {t('common.cancel', 'Cancel')}
        </button>
        <button type="submit" disabled={isSubmitting} className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50">
          {isSubmitting ? t('common.loading', 'Loading...') : t('events.createEvent', 'Create Event')}
        </button>
      </div>
    </form>
  );
}
