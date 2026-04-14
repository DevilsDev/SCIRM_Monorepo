import { useEffect, useState, createContext, useContext } from 'react';
import { XMarkIcon } from '@heroicons/react/24/outline';
import clsx from 'clsx';

interface ToastMessage {
  id: string;
  type: 'info' | 'success' | 'warning' | 'error';
  title: string;
  description?: string;
}

interface ToastContextType {
  addToast: (type: ToastMessage['type'], title: string, description?: string) => void;
}

const ToastContext = createContext<ToastContextType>({ addToast: () => {} });

export function useToast() {
  return useContext(ToastContext);
}

const typeStyles: Record<string, string> = {
  info: 'border-blue-400 bg-blue-50 dark:bg-blue-900/30',
  success: 'border-green-400 bg-green-50 dark:bg-green-900/30',
  warning: 'border-yellow-400 bg-yellow-50 dark:bg-yellow-900/30',
  error: 'border-red-400 bg-red-50 dark:bg-red-900/30',
};

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastMessage[]>([]);

  const addToast = (type: ToastMessage['type'], title: string, description?: string) => {
    const id = Date.now().toString(36) + Math.random().toString(36).slice(2);
    setToasts((prev) => [...prev, { id, type, title, description }]);
  };

  const removeToast = (id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  };

  return (
    <ToastContext.Provider value={{ addToast }}>
      {children}
      {/* Toast container */}
      <div className="fixed top-4 right-4 z-[60] space-y-2 max-w-sm">
        {toasts.map((toast) => (
          <ToastItem key={toast.id} toast={toast} onClose={() => removeToast(toast.id)} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

function ToastItem({ toast, onClose }: { toast: ToastMessage; onClose: () => void }) {
  useEffect(() => {
    const timer = setTimeout(onClose, 5000);
    return () => clearTimeout(timer);
  }, [onClose]);

  return (
    <div className={clsx('border-l-4 rounded-lg shadow-lg p-4 flex items-start gap-3 animate-slide-in', typeStyles[toast.type])}>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold text-gray-900 dark:text-white">{toast.title}</p>
        {toast.description && <p className="text-xs text-gray-600 dark:text-gray-300 mt-0.5">{toast.description}</p>}
      </div>
      <button onClick={onClose} className="p-0.5 hover:bg-gray-200 dark:hover:bg-gray-600 rounded">
        <XMarkIcon className="h-4 w-4 text-gray-400" />
      </button>
    </div>
  );
}
