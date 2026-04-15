import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

export function useKeyboardShortcuts() {
  const navigate = useNavigate();

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      // Don't trigger when typing in inputs
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;

      // ⌘K / Ctrl+K — handled by GlobalSearch
      // Single key shortcuts (no modifier)
      if (!e.metaKey && !e.ctrlKey && !e.altKey) {
        switch (e.key.toLowerCase()) {
          case 'n': navigate('/assessments/new'); break;
          case 'd': navigate('/dashboard'); break;
          case 'r': navigate('/risks'); break;
          case 's': navigate('/suppliers'); break;
          case 'a': navigate('/alerts'); break;
          case '?':
            // Show shortcuts help
            alert('Keyboard Shortcuts:\n\nD — Dashboard\nR — Risks\nS — Suppliers\nA — Alerts\nN — New Assessment\n⌘K — Search\n? — This help');
            break;
        }
      }
    };

    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [navigate]);
}
