// Which tab of the deal page to show. Old links (#/deals/D-1/review, /flow) still work.
export const DEAL_TABS = [
  { id: 'memo', label: 'Memo' },
  { id: 'calculations', label: 'Calculations' },
  { id: 'files', label: 'Files' },
  { id: 'process', label: 'Process' },
] as const

export type DealTab = (typeof DEAL_TABS)[number]['id']

const LEGACY: Record<string, DealTab> = {
  review: 'memo', flow: 'process', numbers: 'calculations',
}
const NEEDS_RESULT: DealTab[] = ['memo', 'calculations']

export function resolveTab(raw: string | undefined, hasResult: boolean): DealTab {
  const wanted = (raw && (LEGACY[raw] ?? DEAL_TABS.find((t) => t.id === raw)?.id)) as DealTab | undefined
  if (wanted) return !hasResult && NEEDS_RESULT.includes(wanted) ? 'process' : wanted
  return hasResult ? 'memo' : 'process'
}
