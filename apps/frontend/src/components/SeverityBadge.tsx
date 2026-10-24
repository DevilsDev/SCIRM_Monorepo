import clsx from 'clsx';
import { useTranslation } from 'react-i18next';

const colorMap: Record<string, string> = {
  low: 'bg-green-100 text-green-800',
  medium: 'bg-yellow-100 text-yellow-800',
  high: 'bg-orange-100 text-orange-800',
  critical: 'bg-red-100 text-red-800',
};

const severityKeys: Record<string, string> = {
  low: 'common.severityLow',
  medium: 'common.severityMedium',
  high: 'common.severityHigh',
  critical: 'common.severityCritical',
};

export default function SeverityBadge({ severity }: { severity: string }) {
  const { t } = useTranslation();
  return (
    <span
      className={clsx(
        'inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium capitalize',
        colorMap[severity] || 'bg-gray-100 dark:bg-gray-700 text-gray-800'
      )}
    >
      {t(severityKeys[severity] || severity, severity)}
    </span>
  );
}
