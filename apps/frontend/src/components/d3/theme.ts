/**
 * D3 theme-aware color palette.
 * Detects dark mode from the <html> element class.
 */

export function isDarkMode(): boolean {
  return document.documentElement.classList.contains('dark');
}

export function getThemeColors() {
  const dark = isDarkMode();
  return {
    text: dark ? '#f9fafb' : '#111827',           // primary text
    textMuted: dark ? '#9ca3af' : '#6b7280',      // secondary text
    textLight: dark ? '#d1d5db' : '#4b5563',      // tertiary / legend
    stroke: dark ? '#1f2937' : '#ffffff',          // arc stroke
    grid: dark ? '#374151' : '#e5e7eb',            // grid lines
    gridLight: dark ? '#1f2937' : '#f3f4f6',       // light grid / cell bg
    background: dark ? '#111827' : '#ffffff',       // chart background
    tooltipBg: '#111827',                          // always dark
    tooltipText: '#ffffff',                        // always white
  };
}
