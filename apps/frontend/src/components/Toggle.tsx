interface ToggleProps {
  enabled: boolean;
  onChange: (value: boolean) => void;
  label?: string;
  description?: string;
}

export default function Toggle({ enabled, onChange, label, description }: ToggleProps) {
  return (
    <div className="flex items-center justify-between">
      {(label || description) && (
        <div>
          {label && <p className="text-sm font-medium text-gray-900 dark:text-white">{label}</p>}
          {description && <p className="text-xs text-gray-500 dark:text-gray-400">{description}</p>}
        </div>
      )}
      <button
        type="button"
        role="switch"
        aria-checked={enabled}
        onClick={() => onChange(!enabled)}
        className={`
          relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full
          border-2 border-transparent transition-colors duration-200 ease-in-out
          focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-500
          ${enabled ? 'bg-blue-600' : 'bg-gray-300 dark:bg-gray-600'}
        `}
        style={{ minHeight: 'unset' }}
      >
        <span
          className={`
            pointer-events-none inline-block h-5 w-5 rounded-full bg-white shadow-sm
            ring-0 transition-transform duration-200 ease-in-out
            ${enabled ? 'translate-x-5' : 'translate-x-0'}
          `}
        />
      </button>
    </div>
  );
}
