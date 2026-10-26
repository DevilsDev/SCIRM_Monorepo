import { useTranslation } from 'react-i18next';
import DatePicker from './DatePicker';

interface DateRangePickerProps {
  from: string;
  to: string;
  onFromChange: (value: string) => void;
  onToChange: (value: string) => void;
  className?: string;
}

export default function DateRangePicker({ from, to, onFromChange, onToChange, className = '' }: DateRangePickerProps) {
  const { t } = useTranslation();

  return (
    <div className={`flex items-center gap-2 ${className}`}>
      <DatePicker value={from} onChange={(e) => onFromChange(e.target.value)} max={to || undefined} />
      <span className="text-sm text-gray-400">{t('common.to', 'to')}</span>
      <DatePicker value={to} onChange={(e) => onToChange(e.target.value)} min={from || undefined} />
    </div>
  );
}
