import { useState, KeyboardEvent } from 'react';
import { XMarkIcon } from '@heroicons/react/24/outline';
import clsx from 'clsx';

interface TagInputProps {
  value: string[];
  onChange: (tags: string[]) => void;
  placeholder?: string;
  error?: boolean;
}

export default function TagInput({ value, onChange, placeholder = 'Type and press Enter...', error }: TagInputProps) {
  const [input, setInput] = useState('');

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && input.trim()) {
      e.preventDefault();
      if (!value.includes(input.trim())) {
        onChange([...value, input.trim()]);
      }
      setInput('');
    }
    if (e.key === 'Backspace' && !input && value.length > 0) {
      onChange(value.slice(0, -1));
    }
  };

  const remove = (tag: string) => onChange(value.filter((t) => t !== tag));

  return (
    <div
      className={clsx(
        'flex flex-wrap items-center gap-1.5 px-3 py-2 border rounded-lg bg-white dark:bg-gray-800 min-h-[38px] transition-colors',
        error ? 'border-red-500' : 'border-gray-300 dark:border-gray-600 focus-within:ring-2 focus-within:ring-blue-500'
      )}
    >
      {value.map((tag) => (
        <span key={tag} className="inline-flex items-center gap-1 px-2 py-0.5 bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 text-xs rounded-full">
          {tag}
          <XMarkIcon className="h-3 w-3 cursor-pointer hover:text-red-500" onClick={() => remove(tag)} />
        </span>
      ))}
      <input
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={value.length === 0 ? placeholder : ''}
        className="flex-1 min-w-[80px] bg-transparent text-sm text-gray-900 dark:text-white outline-none placeholder:text-gray-400"
      />
    </div>
  );
}
