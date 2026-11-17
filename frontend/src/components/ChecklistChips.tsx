import type { Checklist } from '../api/client'

const DOC_LABELS: Record<string, string> = {
  deal_summary: 'Deal summary',
  purchase_contract: 'Contract',
  rent_roll: 'Rent roll',
  t12: 'T-12',
  renovation_budget: 'Renovation budget',
}

const FACT_LABELS: Record<string, string> = {
  property_address: 'address',
  asset_type: 'asset type',
  unit_count: 'unit count',
  loan_amount_requested: 'loan amount',
  purchase_price: 'purchase price',
  renovation_budget: 'renovation budget',
  sponsor_name: 'sponsor',
}

/** Document chips come from the completeness check (code); this only draws them. */
export default function ChecklistChips({ checklist }: { checklist: Checklist | null }) {
  if (!checklist) return null
  return (
    <div>
      <div className="flex flex-wrap gap-2">
        {checklist.required.map((doc) => {
          const done = checklist.received.includes(doc)
          return (
            <span
              key={doc}
              className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-sm ring-1 ring-inset ${
                done
                  ? 'bg-teal-50 text-teal-700 ring-teal-600/20'
                  : 'bg-white text-slate-500 ring-slate-300'
              }`}
            >
              <span aria-hidden>{done ? '✓' : '○'}</span>
              {DOC_LABELS[doc] ?? doc}
            </span>
          )
        })}
      </div>
      {checklist.facts_missing.length > 0 && (
        <p className="mt-2 text-xs text-slate-500">
          Still need to hear: {checklist.facts_missing.map((f) => FACT_LABELS[f] ?? f).join(', ')}
        </p>
      )}
    </div>
  )
}
