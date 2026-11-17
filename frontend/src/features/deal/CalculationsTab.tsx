import { useState } from 'react'
import type { ApiEvent, CheckReport, Deal, UnderwritingResult } from '../../api/client'
import Calculations from './Calculations'
import WorkbookViewer from './WorkbookViewer'

/** The metrics with their formulas and sources, or the workbook behind them. */
export default function CalculationsTab({
  dealId, deal, result, check, events, bust, onViewSource,
}: {
  dealId: string; deal: Deal; result: UnderwritingResult; check: CheckReport | null
  events: ApiEvent[]; bust: string; onViewSource: (doc: string, locator: string) => void
}) {
  const [view, setView] = useState<'metrics' | 'workbook'>('metrics')
  const pill = (id: typeof view, label: string) => (
    <button onClick={() => setView(id)} aria-pressed={view === id}
      className={`border px-3 py-1 text-xs font-semibold ${
        view === id ? 'border-ink bg-ink text-paper' : 'border-slate-300 text-slate-600 hover:border-ink'
      }`}>
      {label}
    </button>
  )
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex gap-1 border-b border-slate-200 bg-white px-5 py-2">
        {pill('metrics', 'Metrics and sources')}
        {pill('workbook', 'Workbook')}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto bg-paper">
        {view === 'metrics' ? (
          <Calculations deal={deal} result={result} check={check} events={events} onViewSource={onViewSource} />
        ) : (
          <WorkbookViewer dealId={dealId} bust={bust} />
        )}
      </div>
    </div>
  )
}
