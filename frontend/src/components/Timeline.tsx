import type { ApiEvent } from '../api/client'
import { clock } from '../lib/format'
import type { Flow, NodeId, NodeState } from '../lib/flow'

const STEPS: { id: NodeId; label: string }[] = [
  { id: 'intake', label: 'Intake' },
  { id: 'extraction', label: 'Extraction' },
  { id: 'underwriter', label: 'Underwriting' },
  { id: 'checker', label: 'Checker' },
  { id: 'reviewer', label: 'Your review' },
]

const DOT: Record<NodeState, string> = {
  idle: 'border-slate-300 bg-white',
  running: 'border-amber-400 bg-amber-300 animate-pulse',
  done: 'border-teal-500 bg-teal-500',
  failed: 'border-coral-500 bg-coral-500',
}

// Tool calls and checklist refreshes are detail for the Flow drawer, not the review timeline.
const QUIET = ['tool.called', 'checklist.updated', 'file.classified', 'fact.recorded']

export default function Timeline({ flow, events }: { flow: Flow; events: ApiEvent[] }) {
  const feed = events.filter((e) => !QUIET.includes(e.type)).slice(-40).reverse()
  return (
    <div className="flex h-full flex-col">
      <ol className="space-y-0 p-4">
        {STEPS.map((s, i) => (
          <li key={s.id} className="relative flex gap-3 pb-5 last:pb-0">
            {i < STEPS.length - 1 && <span className="absolute left-[7px] top-4 h-full w-px bg-slate-200" />}
            <span className={`relative z-10 mt-0.5 h-4 w-4 shrink-0 rounded-full border-2 ${DOT[flow.nodes[s.id].state]}`} />
            <div>
              <div className="text-sm font-medium">{s.label}</div>
              <div className="text-xs text-slate-500">{flow.nodes[s.id].note}</div>
            </div>
          </li>
        ))}
      </ol>
      <div className="border-t border-slate-200 px-4 pb-1 pt-3 text-xs font-semibold uppercase tracking-wide text-slate-500">
        Activity
      </div>
      <ul className="min-h-0 flex-1 space-y-1.5 overflow-y-auto px-4 pb-4 text-xs">
        {feed.map((e) => (
          <li key={e.event_id} className="flex gap-2">
            <span className="shrink-0 text-slate-400">{clock(e.ts)}</span>
            <span className="text-slate-700">{e.summary}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
