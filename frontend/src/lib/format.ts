export const usd = (n: number | null | undefined) =>
  n == null ? '–' : `${n < 0 ? '-' : ''}$${Math.abs(Math.round(n)).toLocaleString('en-US')}`

export const pct = (n: number | null | undefined, digits = 2) =>
  n == null ? '–' : `${(n * 100).toFixed(digits)}%`

export const mult = (n: number | null | undefined) => (n == null ? '–' : `${n.toFixed(2)}x`)

export function ago(iso: string | undefined): string {
  if (!iso) return ''
  const secs = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000))
  if (secs < 60) return `${secs}s`
  if (secs < 3600) return `${Math.round(secs / 60)}m`
  if (secs < 86400) return `${Math.round(secs / 3600)}h`
  return `${Math.round(secs / 86400)}d`
}

export const clock = (iso: string) =>
  new Date(iso).toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })

const RATIOS = [
  'ltc', 'ltv_as_is', 'loan_to_arv', 'debt_yield_stabilized', 'implied_cap_rate',
  'rent_roll_vs_t12', 'sources_vs_uses',
]

/** Show a metric in the unit its name implies. */
export function metricValue(key: string, v: number): string {
  if (key.includes('dscr')) return mult(v)
  if (RATIOS.includes(key)) return pct(v)
  return usd(v)
}

export const LABELS: Record<string, string> = {
  total_cost: 'Total cost',
  ltc: 'Loan to cost',
  ltv_as_is: 'Loan to value (as-is)',
  loan_to_arv: 'Loan to ARV',
  dscr_in_place: 'In-place DSCR',
  debt_yield_stabilized: 'Debt yield (stabilized)',
  implied_cap_rate: 'Implied cap rate',
}

/** Format a spreadsheet cell using its Excel number format. */
export function cellText(value: unknown, format: string): string {
  if (value == null) return ''
  if (typeof value !== 'number') return String(value)
  if (format.includes('%')) return pct(value)
  if (format.includes('"x"')) return mult(value)
  if (format === '#,##0') return Math.round(value).toLocaleString('en-US')
  if (format === '#,##0.00') return value.toLocaleString('en-US', { minimumFractionDigits: 2 })
  if (Number.isInteger(value)) return String(value)
  return value.toLocaleString('en-US', { maximumFractionDigits: 4 })
}
