import { useMemo, useState } from 'react'
import { api } from '../api/client'
import { useDealData } from '../api/hooks'
import ChiefChat from '../components/ChiefChat'
import { CallChip, Chip, EscalationBadge, StateChip } from '../components/Chips'
import DecisionBar from '../components/DecisionBar'
import DecisionPackage from '../components/DecisionPackage'
import FlowGraph from '../components/FlowGraph'
import MemoViewer from '../components/MemoViewer'
import NodeDrawer from '../components/NodeDrawer'
import { Page } from '../components/Shell'
import Timeline from '../components/Timeline'
import WorkbookViewer from '../components/WorkbookViewer'
import { deriveFlow } from '../lib/flow'
import type { NodeId } from '../lib/flow'
import { navigate } from '../lib/router'

type Tab = 'flow' | 'review'
type Pane = 'memo' | 'workbook' | 'sources'

const DONE = ['NEEDS_REVIEW', 'APPROVED', 'RELEASED', 'REJECTED']

/** The deal name; click to rename. Enter saves, Escape cancels. */
function DealTitle({ dealId, name, onSaved }: { dealId: string; name: string; onSaved: () => void }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(name)
  const [error, setError] = useState<string | null>(null)

  const save = async () => {
    const next = draft.trim()
    if (!next || next === name) {
      setEditing(false)
      setError(null)
      return
    }
    try {
      await api.rename(dealId, next)
      setEditing(false)
      setError(null)
      onSaved()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  if (editing)
    return (
      <div>
        <input
          autoFocus
          value={draft}
          maxLength={80}
          aria-label="Deal name"
          onChange={(e) => setDraft(e.target.value)}
          onBlur={() => void save()}
          onKeyDown={(e) => {
            if (e.key === 'Enter') void save()
            if (e.key === 'Escape') {
              setEditing(false)
              setError(null)
            }
          }}
          className="w-80 border-b border-ink bg-transparent text-[22px] font-bold tracking-tight outline-none"
        />
        {error && <div className="text-xs text-coral-700">{error}</div>}
      </div>
    )
  return (
    <button
      onClick={() => {
        setDraft(name)
        setEditing(true)
      }}
      title="Click to rename"
      className="group flex items-baseline gap-2 text-left"
    >
      <h1 className="text-[22px] leading-tight">{name || 'Untitled deal'}</h1>
      <span className="text-xs font-semibold text-slate-400 opacity-0 transition-opacity group-hover:opacity-100">
        Rename
      </span>
    </button>
  )
}

export default function Workspace({ dealId, tab }: { dealId: string; tab?: string }) {
  const { detail, events, error, reload } = useDealData(dealId)
  const [pane, setPane] = useState<Pane>('memo')
  const [selected, setSelected] = useState<NodeId | null>(null)
  const [archiveError, setArchiveError] = useState<string | null>(null)
  const flow = useMemo(() => deriveFlow(events), [events])

  if (error && !detail)
    return (
      <Page active="queue">
        <div className="p-8 text-sm">
          <p className="text-coral-700">Could not load {dealId}: {error}</p>
          <a className="font-semibold underline underline-offset-4" href="#/">Back to the queue</a>
        </div>
      </Page>
    )
  if (!detail)
    return (
      <Page active="queue">
        <div className="p-8 text-sm text-slate-400">Loading {dealId}…</div>
      </Page>
    )

  const status = detail.status
  const state = status.state
  const active: Tab = tab === 'review' || tab === 'flow' ? tab : DONE.includes(state) ? 'review' : 'flow'
  const hasResult = !!(detail.deal && detail.result)
  const bust = `${status.deal_version}-${events.filter((e) => e.type === 'memo.rendered' || e.type === 'underwriting.completed').length}`

  const archive = async () => {
    setArchiveError(null)
    try {
      await api.archive(dealId)
      navigate('')
    } catch (e) {
      setArchiveError((e as Error).message)
    }
  }

  const tabClass = (on: boolean) =>
    `-mb-px border-b-2 px-1 pb-2 text-sm font-semibold transition-colors ${
      on ? 'border-ink text-ink' : 'border-transparent text-slate-500 hover:text-ink'
    }`

  return (
    <Page active="queue">
      <div className="flex h-full flex-col">
        <div className="border-b border-slate-200 bg-paper px-6 pt-3">
          <div className="flex items-center gap-3 text-xs text-slate-500">
            <a href="#/" className="font-semibold hover:text-ink">← Deal queue</a>
            <span>/</span>
            <span>{dealId} · version {status.deal_version}</span>
            <button
              onClick={() => void archive()}
              className="ml-auto font-semibold text-slate-500 underline-offset-4 hover:text-ink hover:underline"
              title="Hide this deal from the queue. It is kept and can be restored."
            >
              Archive deal
            </button>
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-3">
            <DealTitle key={status.name} dealId={dealId} name={status.name} onSaved={reload} />
            <StateChip state={state} />
            <CallChip call={status.call} />
            {status.escalation && <EscalationBadge />}
            {status.retry_count > 0 && !status.escalation && (
              <Chip tone="amber">retry {status.retry_count} of 2</Chip>
            )}
          </div>
          {archiveError && <p className="mt-1 text-xs text-coral-700">{archiveError}</p>}
          <nav className="mt-3 flex gap-6">
            {([['flow', 'Flow'], ['review', 'Review']] as [Tab, string][]).map(([t, label]) => (
              <button key={t} onClick={() => navigate(`deals/${dealId}/${t}`)} className={tabClass(active === t)}>
                {label}
              </button>
            ))}
          </nav>
        </div>

        <div className="flex min-h-0 flex-1">
          <main className="relative min-w-0 flex-1">
            {active === 'flow' ? (
              <div className="relative h-full">
                <FlowGraph flow={flow} selected={selected} onSelect={setSelected} />
                <div className="pointer-events-none absolute bottom-4 left-6 max-w-md text-xs leading-relaxed text-slate-500">
                  Agents never call each other: every handoff goes through the chief and is logged.
                  Click a node to see its handoffs and tool calls.
                </div>
                {state === 'NEEDS_REVIEW' && (
                  <button
                    onClick={() => navigate(`deals/${dealId}/review`)}
                    className="absolute right-6 top-5 rounded-[2px] border border-ink bg-ink px-4 py-1.5 text-sm font-semibold text-paper hover:bg-slate-700"
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
                <div className="w-60 shrink-0 border-r border-slate-200 bg-paper">
                  <Timeline flow={flow} events={events} />
                </div>
                <div className="flex min-w-0 flex-1 flex-col">
                  <DecisionBar dealId={dealId} state={state} escalated={status.escalation} />
                  <div className="flex gap-6 border-b border-slate-200 bg-paper px-5 pt-2.5">
                    {(
                      [['memo', 'Memo'], ['workbook', 'Workbook'], ['sources', 'Metrics and sources']] as [Pane, string][]
                    ).map(([id, label]) => (
                      <button key={id} onClick={() => setPane(id)} className={tabClass(pane === id)}>
                        {label}
                      </button>
                    ))}
                  </div>
                  <div className="min-h-0 flex-1 overflow-y-auto bg-paper">
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
    </Page>
  )
}
