import { useMemo, useState } from 'react'
import { useDealData } from '../api/hooks'
import ChiefChat from '../components/ChiefChat'
import { CallChip, Chip, EscalationBadge, StateChip } from '../components/Chips'
import DecisionBar from '../components/DecisionBar'
import DecisionPackage from '../components/DecisionPackage'
import FlowGraph from '../components/FlowGraph'
import MemoViewer from '../components/MemoViewer'
import NodeDrawer from '../components/NodeDrawer'
import Timeline from '../components/Timeline'
import WorkbookViewer from '../components/WorkbookViewer'
import { deriveFlow } from '../lib/flow'
import type { NodeId } from '../lib/flow'
import { navigate } from '../lib/router'

type Tab = 'flow' | 'review'
type Pane = 'memo' | 'workbook' | 'sources'

const DONE = ['NEEDS_REVIEW', 'APPROVED', 'RELEASED', 'REJECTED']

export default function Workspace({ dealId, tab }: { dealId: string; tab?: string }) {
  const { detail, events, error } = useDealData(dealId)
  const [pane, setPane] = useState<Pane>('memo')
  const [selected, setSelected] = useState<NodeId | null>(null)
  const flow = useMemo(() => deriveFlow(events), [events])

  if (error && !detail)
    return (
      <div className="p-8 text-sm">
        <p className="text-coral-700">Could not load {dealId}: {error}</p>
        <a className="text-teal-700 hover:underline" href="#/">← Back to the queue</a>
      </div>
    )
  if (!detail) return <div className="p-8 text-sm text-slate-400">Loading {dealId}…</div>

  const status = detail.status
  const state = status.state
  const active: Tab = tab === 'review' || tab === 'flow' ? tab : DONE.includes(state) ? 'review' : 'flow'
  const hasResult = !!(detail.deal && detail.result)
  const bust = `${status.deal_version}-${events.filter((e) => e.type === 'memo.rendered' || e.type === 'underwriting.completed').length}`

  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center gap-4 border-b border-slate-200 bg-white px-5 py-3">
        <a href="#/" className="text-sm text-slate-500 hover:text-slate-900">← Queue</a>
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-base font-semibold">{status.name || 'Untitled deal'}</h1>
            <span className="text-xs text-slate-400">{dealId} · v{status.deal_version}</span>
          </div>
        </div>
        <StateChip state={state} />
        <CallChip call={status.call} />
        {status.escalation && <EscalationBadge />}
        {status.retry_count > 0 && !status.escalation && (
          <Chip tone="amber">retry {status.retry_count} of 2</Chip>
        )}
        <nav className="ml-auto flex rounded-lg bg-slate-100 p-0.5 text-sm">
          {(['flow', 'review'] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => navigate(`deals/${dealId}/${t}`)}
              className={`rounded-md px-4 py-1.5 font-medium capitalize ${
                active === t ? 'bg-white shadow-sm' : 'text-slate-500 hover:text-slate-800'
              }`}
            >
              {t}
            </button>
          ))}
        </nav>
      </header>

      <div className="flex min-h-0 flex-1">
        <main className="relative min-w-0 flex-1">
          {active === 'flow' ? (
            <div className="relative h-full">
              <FlowGraph flow={flow} selected={selected} onSelect={setSelected} />
              <div className="pointer-events-none absolute bottom-3 left-4 max-w-md text-xs text-slate-500">
                Agents never call each other: every handoff goes through the chief and is logged.
                Click a node to see its handoffs and tool calls.
              </div>
              {state === 'NEEDS_REVIEW' && (
                <button
                  onClick={() => navigate(`deals/${dealId}/review`)}
                  className="absolute right-4 top-4 rounded-md bg-teal-600 px-3 py-1.5 text-sm font-medium text-white shadow hover:bg-teal-700"
                >
                  Ready for review →
                </button>
              )}
              {selected && (
                <NodeDrawer node={selected} events={events} flow={flow} onClose={() => setSelected(null)} />
              )}
            </div>
          ) : (
            <div className="flex h-full">
              <div className="w-60 shrink-0 border-r border-slate-200 bg-white">
                <Timeline flow={flow} events={events} />
              </div>
              <div className="flex min-w-0 flex-1 flex-col">
                <DecisionBar dealId={dealId} state={state} escalated={status.escalation} />
                <div className="flex gap-1 border-b border-slate-200 bg-slate-50 px-3 pt-2">
                  {(
                    [['memo', 'Memo'], ['workbook', 'Workbook'], ['sources', 'Metrics and sources']] as [Pane, string][]
                  ).map(([id, label]) => (
                    <button
                      key={id}
                      onClick={() => setPane(id)}
                      className={`rounded-t-md px-4 py-1.5 text-sm font-medium ${
                        pane === id ? 'bg-white text-slate-900 ring-1 ring-slate-200' : 'text-slate-500 hover:text-slate-800'
                      }`}
                    >
                      {label}
                    </button>
                  ))}
                </div>
                <div className="min-h-0 flex-1 overflow-y-auto bg-white">
                  {!hasResult ? (
                    <p className="p-8 text-sm text-slate-500">
                      Nothing to review yet. The deal is {state.replaceAll('_', ' ').toLowerCase()}.
                    </p>
                  ) : pane === 'memo' ? (
                    <MemoViewer dealId={dealId} bust={bust} />
                  ) : pane === 'workbook' ? (
                    <WorkbookViewer dealId={dealId} bust={bust} />
                  ) : (
                    <DecisionPackage deal={detail.deal!} result={detail.result!} check={detail.check ?? null} events={events} />
                  )}
                </div>
              </div>
            </div>
          )}
        </main>
        <aside className="w-[380px] shrink-0 border-l border-slate-200 bg-white">
          <ChiefChat key={dealId} dealId={dealId} enabled={hasResult} pending={detail.pending_patches} />
        </aside>
      </div>
    </div>
  )
}
