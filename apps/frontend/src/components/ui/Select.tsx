import { SelectHTMLAttributes, forwardRef } from 'react';
import clsx from 'clsx';

interface SelectOption {
  value: string;
  label: string;
}

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  options: SelectOption[];
  placeholder?: string;
  error?: boolean;
}

const Select = forwardRef<HTMLSelectElement, SelectProps>(({ options, placeholder, error, className, ...props }, ref) => {
  return (
    <select
      ref={ref}
      className={clsx(
        'w-full px-3 py-2 border rounded-lg text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-white transition-colors outline-none appearance-none',
        error
          ? 'border-red-500 focus:ring-2 focus:ring-red-500'
          : 'border-gray-300 dark:border-gray-600 focus:ring-2 focus:ring-blue-500 focus:border-blue-500',
        className
      )}
      {...props}
    >
      {placeholder && <option value="">{placeholder}</option>}
      {options.map((opt) => (
        <option key={opt.value} value={opt.value}>{opt.label}</option>
      ))}
    </select>
  );
});

Select.displayName = 'Select';
export default Select;
