import clsx from 'clsx';

interface SliderProps {
  value: number;
  onChange: (value: number) => void;
  min?: number;
  max?: number;
  step?: number;
  label?: string;
  showValue?: boolean;
  suffix?: string;
  className?: string;
}

export default function Slider({ value, onChange, min = 0, max = 100, step = 1, label, showValue = true, suffix = '', className }: SliderProps) {
  const pct = ((value - min) / (max - min)) * 100;

  return (
    <div className={clsx('space-y-1', className)}>
      {(label || showValue) && (
        <div className="flex items-center justify-between">
          {label && <span className="text-sm font-medium text-gray-700 dark:text-gray-300">{label}</span>}
          {showValue && <span className="text-sm font-semibold text-gray-900 dark:text-white">{value}{suffix}</span>}
        </div>
      )}
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full h-2 bg-gray-200 dark:bg-gray-700 rounded-full appearance-none cursor-pointer accent-blue-600"
        style={{ background: `linear-gradient(to right, #2563eb ${pct}%, ${pct}% 100%)` }}
      />
    </div>
  );
}
