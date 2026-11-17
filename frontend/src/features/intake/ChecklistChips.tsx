import type { Checklist } from '../../api/client'

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
  // Before the first message there is no deal yet, so show the five required documents as empty.
  const view = checklist ?? { required: Object.keys(DOC_LABELS), received: [], facts_missing: [] }
  return (
    <div>
      <div className="flex flex-wrap gap-2">
        {view.required.map((doc) => {
          const done = view.received.includes(doc)
          return (
            <span
              key={doc}
              className={`inline-flex items-center gap-2 rounded-[2px] border px-3 py-1 text-sm font-semibold ${
                done ? 'border-teal-600/50 text-teal-700' : 'border-slate-300 text-slate-500'
              }`}
            >
              <span aria-hidden className={`h-2 w-2 ${done ? 'bg-teal-600' : 'border border-slate-400'}`} />
              {DOC_LABELS[doc] ?? doc}
            </span>
          )
        })}
      </div>
      {view.facts_missing.length > 0 && (
        <p className="mt-2 text-xs text-slate-500">
          Still need to hear: {view.facts_missing.map((f) => FACT_LABELS[f] ?? f).join(', ')}
        </p>
      )}
    </div>
  )
}
