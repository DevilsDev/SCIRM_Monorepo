import { InputHTMLAttributes, forwardRef } from 'react';
import clsx from 'clsx';

interface DatePickerProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> {
  error?: boolean;
}

const DatePicker = forwardRef<HTMLInputElement, DatePickerProps>(({ error, className, ...props }, ref) => {
  return (
    <input
      ref={ref}
      type="date"
      className={clsx(
        'w-full px-3 py-2 border rounded-lg text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-white transition-colors outline-none',
        error
          ? 'border-red-500 focus:ring-2 focus:ring-red-500'
          : 'border-gray-300 dark:border-gray-600 focus:ring-2 focus:ring-blue-500 focus:border-blue-500',
        className
      )}
      {...props}
    />
  );
});

DatePicker.displayName = 'DatePicker';
export default DatePicker;
