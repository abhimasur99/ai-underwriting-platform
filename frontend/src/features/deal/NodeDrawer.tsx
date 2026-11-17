import type { ApiEvent } from '../../api/client'
import { clock } from '../../lib/format'
import { nodeActivity } from '../../lib/flow'
import type { Flow, NodeId } from '../../lib/flow'
import { Chip } from '../../ui/Chip'

const TITLES: Record<NodeId, string> = {
  intake: 'Intake chat',
  chief: 'Chief',
  extraction: 'Extraction agent',
  underwriter: 'Underwriter agent',
  checker: 'Checker agent',
  reviewer: 'Human reviewer',
}

function show(v: unknown): string {
  if (v == null) return '–'
  if (typeof v === 'number') return Number.isInteger(v) ? v.toLocaleString('en-US') : String(+v.toPrecision(7))
  if (typeof v === 'string') return v
  return JSON.stringify(v)
}

function ToolRow({ e }: { e: ApiEvent }) {
  const p = e.payload as { tool?: string; inputs?: Record<string, unknown>; formula?: string; output?: unknown; call_id?: string }
  const inputs = Object.entries(p.inputs ?? {})
  return (
    <details className="group rounded-md border border-slate-200 bg-white">
      <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2 text-xs">
        <span className="text-slate-400 group-open:rotate-90">▸</span>
        <span className="font-mono font-medium text-slate-800">{p.tool}</span>
        <span className="ml-auto truncate text-slate-500">{e.summary.replace(`${p.tool} = `, '= ')}</span>
      </summary>
      <div className="space-y-1.5 border-t border-slate-100 px-3 py-2 text-xs">
        {p.formula && (
          <div>
            <span className="text-slate-400">formula </span>
            <code className="rounded bg-slate-100 px-1.5 py-0.5">{p.formula}</code>
          </div>
        )}
        {inputs.length > 0 && (
          <div>
            <div className="text-slate-400">inputs</div>
            {inputs.map(([k, v]) => (
              <div key={k} className="font-mono">
                {k} = <span className="text-slate-700">{show(v).slice(0, 160)}</span>
              </div>
            ))}
          </div>
        )}
        <div>
          <span className="text-slate-400">output </span>
          <span className="font-mono">{show(p.output).slice(0, 200)}</span>
        </div>
        <div className="text-slate-400">
          {p.call_id} · {clock(e.ts)}
        </div>
      </div>
    </details>
  )
}

export default function NodeDrawer({
  node,
  events,
  flow,
  onClose,
}: {
  node: NodeId
  events: ApiEvent[]
  flow: Flow
  onClose: () => void
}) {
  const { handoffs, tools, other } = nodeActivity(events, node)
  const info = flow.nodes[node]
  return (
    <aside className="absolute right-0 top-0 z-10 flex h-full w-96 flex-col border-l border-slate-200 bg-slate-50 shadow-xl">
      <div className="flex items-center gap-2 border-b border-slate-200 bg-white px-4 py-3">
        <h3 className="font-semibold">{TITLES[node]}</h3>
        <Chip tone={info.state === 'done' ? 'teal' : info.state === 'running' ? 'amber' : info.state === 'failed' ? 'coral' : 'slate'}>
          {info.state}
        </Chip>
        <button onClick={onClose} className="ml-auto text-slate-400 hover:text-slate-700" aria-label="Close">
          ✕
        </button>
      </div>
      <div className="flex-1 space-y-5 overflow-y-auto p-4 text-sm">
        {handoffs.length > 0 && (
          <section>
            <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
              Handoffs
            </h4>
            <div className="space-y-2">
              {handoffs.map(({ sent, returned }) => {
                const s = sent.payload as Record<string, unknown>
                const r = (returned?.payload ?? null) as Record<string, unknown> | null
                return (
                  <div key={sent.event_id} className="rounded-md border border-slate-200 bg-white p-3 text-xs">
                    <div className="flex items-center gap-2">
                      <span className="font-mono font-medium">{show(s.handoff_id)}</span>
                      <span className="text-slate-500">
                        {show(s.from)} → {show(s.to)}
                      </span>
                      <span className="ml-auto text-slate-400">{clock(sent.ts)}</span>
                    </div>
                    <div className="mt-1.5 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-slate-600">
                      <span className="text-slate-400">task</span>
                      <span className="font-mono">{show(s.task)}</span>
                      <span className="text-slate-400">version</span>
                      <span>v{show(s.deal_version)} · attempt {show(s.attempt)}</span>
                      <span className="text-slate-400">inputs</span>
                      <span className="font-mono">{show(s.inputs_ref)}</span>
                      {r ? (
                        <>
                          <span className="text-slate-400">returned</span>
                          <span>
                            {show(r.status)} in {show(r.duration_ms)} ms
                          </span>
                          <span className="text-slate-400">result</span>
                          <span>{show(r.summary) || show(r.outputs_ref)}</span>
                        </>
                      ) : (
                        <>
                          <span className="text-slate-400">returned</span>
                          <span className="text-amber-700">in flight…</span>
                        </>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          </section>
        )}
        {tools.length > 0 && (
          <section>
            <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
              Tool calls ({tools.length})
            </h4>
            <div className="space-y-1.5">
              {tools.map((e) => (
                <ToolRow key={e.event_id} e={e} />
              ))}
            </div>
          </section>
        )}
        {other.length > 0 && (
          <section>
            <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
              Events
            </h4>
            <ul className="space-y-1 text-xs">
              {other.map((e) => (
                <li key={e.event_id} className="flex gap-2">
                  <span className="shrink-0 text-slate-400">{clock(e.ts)}</span>
                  <span className="text-slate-700">{e.summary}</span>
                </li>
              ))}
            </ul>
          </section>
        )}
        {handoffs.length + tools.length + other.length === 0 && (
          <p className="text-slate-500">Nothing has happened here yet.</p>
        )}
      </div>
    </aside>
  )
}
