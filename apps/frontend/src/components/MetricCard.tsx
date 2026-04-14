import React from 'react';
import { ArrowUpIcon, ArrowDownIcon } from '@heroicons/react/24/solid';
import clsx from 'clsx';

interface MetricCardProps {
  title: string;
  value: string | number;
  icon: React.ComponentType<{ className?: string }>;
  color: 'red' | 'green' | 'blue' | 'yellow' | 'purple';
  trend?: {
    value: number;
    isPositive: boolean;
  };
}

const colorClasses = {
  red: { icon: 'text-red-600', bg: 'bg-red-50 dark:bg-red-900/30' },
  green: { icon: 'text-green-600', bg: 'bg-green-50 dark:bg-green-900/30' },
  blue: { icon: 'text-blue-600', bg: 'bg-blue-50 dark:bg-blue-900/30' },
  yellow: { icon: 'text-yellow-600', bg: 'bg-yellow-50 dark:bg-yellow-900/30' },
  purple: { icon: 'text-purple-600', bg: 'bg-purple-50 dark:bg-purple-900/30' },
};

const MetricCard: React.FC<MetricCardProps> = ({ title, value, icon: Icon, color, trend }) => {
  const classes = colorClasses[color];

  return (
    <div className="bg-white dark:bg-gray-800 overflow-hidden shadow rounded-lg border border-gray-200 dark:border-gray-700">
      <div className="p-5">
        <div className="flex items-center">
          <div className="flex-shrink-0">
            <div className={clsx('p-3 rounded-md', classes.bg)}>
              <Icon className={clsx('h-6 w-6', classes.icon)} />
            </div>
          </div>
          <div className="ml-5 w-0 flex-1">
            <dl>
              <dt className="text-sm font-medium text-gray-500 dark:text-gray-400 truncate">{title}</dt>
              <dd className="flex items-baseline">
                <div className="text-2xl font-semibold text-gray-900 dark:text-white">{value}</div>
                {trend && (
                  <div className={clsx('ml-2 flex items-baseline text-sm font-semibold', trend.isPositive ? 'text-green-600' : 'text-red-600')}>
                    {trend.isPositive ? (
                      <ArrowUpIcon className="self-center flex-shrink-0 h-4 w-4 text-green-500" />
                    ) : (
                      <ArrowDownIcon className="self-center flex-shrink-0 h-4 w-4 text-red-500" />
                    )}
                    {trend.value}%
                  </div>
                )}
              </dd>
            </dl>
          </div>
        </div>
      </div>
    </div>
  );
};

export default MetricCard;
