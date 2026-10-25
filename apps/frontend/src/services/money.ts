// Money is always shown in its own currency. Amounts in different currencies are never
// converted or added together: SCIRM has no exchange rates, and a mixed sum would be wrong.

/** An amount in its own currency, e.g. "€1,000.50"; an unknown code is shown as "1000.50 XYZ". */
export function formatMoney(amount: string | number, currency: string): string {
  const n = Number(amount);
  if (!Number.isFinite(n)) return `${amount} ${currency}`;
  try {
    return new Intl.NumberFormat(undefined, { style: 'currency', currency, maximumFractionDigits: 2 }).format(n);
  } catch {
    return `${amount} ${currency}`;
  }
}

/** Totals per currency of several {currency: amount} maps. */
export function sumByCurrency(maps: Array<Record<string, string | number> | null | undefined>): Record<string, number> {
  const totals: Record<string, number> = {};
  for (const map of maps) {
    for (const [currency, amount] of Object.entries(map || {})) {
      const n = Number(amount);
      if (Number.isFinite(n)) totals[currency] = (totals[currency] || 0) + n;
    }
  }
  return totals;
}

/** "€10,000.00 + ¥3,000,000", or the fallback when there is nothing. */
export function formatTotals(totals: Record<string, string | number>, fallback = '-'): string {
  const parts = Object.keys(totals).sort().map((c) => formatMoney(totals[c], c));
  return parts.length ? parts.join(' + ') : fallback;
}
