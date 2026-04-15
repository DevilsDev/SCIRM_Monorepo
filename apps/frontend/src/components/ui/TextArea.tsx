import { TextareaHTMLAttributes, forwardRef } from 'react';
import clsx from 'clsx';

interface TextAreaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  error?: boolean;
  showCount?: boolean;
  maxLength?: number;
}

const TextArea = forwardRef<HTMLTextAreaElement, TextAreaProps>(({ error, showCount, maxLength, className, value, ...props }, ref) => {
  const len = typeof value === 'string' ? value.length : 0;

  return (
    <div className="relative">
      <textarea
        ref={ref}
        value={value}
        maxLength={maxLength}
        className={clsx(
          'w-full px-3 py-2 border rounded-lg text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-white transition-colors outline-none resize-y min-h-[80px]',
          error
            ? 'border-red-500 focus:ring-2 focus:ring-red-500'
            : 'border-gray-300 dark:border-gray-600 focus:ring-2 focus:ring-blue-500 focus:border-blue-500',
          className
        )}
        {...props}
      />
      {showCount && maxLength && (
        <span className="absolute bottom-2 right-2 text-[10px] text-gray-400">{len}/{maxLength}</span>
      )}
    </div>
  );
});

TextArea.displayName = 'TextArea';
export default TextArea;
