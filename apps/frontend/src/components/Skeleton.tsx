import clsx from 'clsx';

interface SkeletonProps {
  className?: string;
  count?: number;
}

function SkeletonLine({ className }: { className?: string }) {
  return (
    <div className={clsx('animate-pulse bg-gray-200 dark:bg-gray-700 rounded', className)} />
  );
}

export function SkeletonCard() {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-5 space-y-3">
      <SkeletonLine className="h-4 w-1/3" />
      <SkeletonLine className="h-8 w-1/2" />
      <SkeletonLine className="h-3 w-2/3" />
    </div>
  );
}

export function SkeletonTable({ rows = 5 }: { rows?: number }) {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 overflow-hidden">
      <div className="px-6 py-3 bg-gray-50 dark:bg-gray-900 flex gap-6">
        {[...Array(5)].map((_, i) => <SkeletonLine key={i} className="h-3 w-20" />)}
      </div>
      {[...Array(rows)].map((_, i) => (
        <div key={i} className="px-6 py-4 flex gap-6 border-t border-gray-100 dark:border-gray-700">
          {[...Array(5)].map((_, j) => <SkeletonLine key={j} className="h-3 w-24" />)}
        </div>
      ))}
    </div>
  );
}

export function SkeletonChart({ height = 200 }: { height?: number }) {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
      <SkeletonLine className="h-5 w-1/4 mb-4" />
      <div className="animate-pulse bg-gray-200 dark:bg-gray-700 rounded-lg" style={{ height }} />
    </div>
  );
}

export default function Skeleton({ className, count = 1 }: SkeletonProps) {
  return (
    <div className="space-y-3">
      {[...Array(count)].map((_, i) => (
        <SkeletonLine key={i} className={className || 'h-4 w-full'} />
      ))}
    </div>
  );
}
