/**
 * D3 theme-aware color palette.
 * Detects dark mode from the <html> element class.
 */

/**
 * Escape a value for interpolation into tooltip HTML built with d3 `.html()`.
 * Labels come from user- and LLM-supplied data (supplier names, risk titles),
 * so every interpolated value must pass through this.
 */
export function esc(value: unknown): string {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

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
