import type { ApiEvent } from '../../api/client'
import type { Flow, NodeId } from '../../lib/flow'
import FlowGraph from './FlowGraph'
import NodeDrawer from './NodeDrawer'
import ProcessLog from './ProcessLog'

/** How the deal was produced: the agents and their handoffs, and a plain-words history. */
export default function ProcessTab({
  flow, events, selected, onSelect,
}: { flow: Flow; events: ApiEvent[]; selected: NodeId | null; onSelect: (id: NodeId | null) => void }) {
  return (
    <div className="flex h-full min-h-0">
      <div className="relative min-w-0 flex-1">
        <FlowGraph flow={flow} selected={selected} onSelect={onSelect} />
        <p className="pointer-events-none absolute bottom-4 left-6 max-w-md text-xs leading-relaxed text-slate-600">
          Agents never call each other: every handoff goes through the chief and is logged. Click a
          node to see its handoffs and tool calls.
        </p>
        {selected && <NodeDrawer node={selected} events={events} flow={flow} onClose={() => onSelect(null)} />}
      </div>
      <div className="w-80 shrink-0 border-l border-slate-200 bg-white">
        <ProcessLog events={events} />
      </div>
    </div>
  )
}
