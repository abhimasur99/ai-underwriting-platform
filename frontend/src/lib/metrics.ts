// Lookups that connect a metric on screen to the tool call that produced it (formula, inputs) and
// to the document line each input came from.
import type { ApiEvent, Deal, UnderwritingResult } from '../api/client'

export interface SourceInfo {
  doc?: string | null
  locator?: string | null
  quote?: string | null
  kind: string
  confidence: number
  value: unknown
}

type Sourced = { value: unknown; source: Deal['sponsor']['name']['source']; confidence: number }

const TOOL_FOR: Record<string, string> = {
  total_cost: 'calc.total_cost',
  ltc: 'calc.ltc',
  ltv_as_is: 'calc.ltv_as_is',
  loan_to_arv: 'calc.loan_to_arv',
  dscr_in_place: 'calc.dscr_in_place',
  debt_yield_stabilized: 'calc.debt_yield',
  implied_cap_rate: 'calc.implied_cap_rate',
  exit_dscr: 'exit.analyze',
  takeout_max: 'exit.analyze',
  refi_cushion: 'exit.analyze',
  refi_cushion_stress: 'exit.stress',
  rent_roll_vs_t12: 'reconcile.all',
  sources_vs_uses: 'reconcile.all',
}

export function toolCallFor(metric: string, events: ApiEvent[], version: number): ApiEvent | null {
  const tool = TOOL_FOR[metric]
  if (!tool) return null
  for (let i = events.length - 1; i >= 0; i--) {
    const e = events[i]
    if (e.type === 'tool.called' && e.actor === 'underwriter' && e.deal_version === version &&
      (e.payload as { tool?: string }).tool === tool) return e
  }
  return null
}

/** The sourced deal field behind a tool input name, when there is one. */
export function sourceFor(deal: Deal, input: string): SourceInfo | null {
  const fields: Record<string, Sourced | undefined> = {
    loan_commitment: deal.loan_request.loan_commitment,
    initial_advance: deal.loan_request.initial_advance,
    note_rate: deal.loan_request.note_rate,
    as_is_value: deal.valuation.as_is_value,
    arv: deal.valuation.arv,
    stabilized_noi: deal.pro_forma.stabilized_noi,
    in_place_noi: deal.t12.in_place_noi,
    noi: deal.pro_forma.stabilized_noi,
    purchase_price: deal.purchase.purchase_price,
    renovation_budget: deal.renovation.renovation_budget,
  }
  const f = fields[input]
  if (!f) return null
  return { ...f.source, confidence: f.confidence, value: f.value }
}

export function ruleCheckMetric(result: UnderwritingResult, key: string) {
  return result.rule_checks.find((c) => c.metric === key)
}
