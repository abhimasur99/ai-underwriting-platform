import { useMemo } from 'react'
import { Background, ConnectionMode, Handle, MarkerType, Position, ReactFlow } from '@xyflow/react'
import type { Edge, Node, NodeProps } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import type { Flow, NodeId, NodeState } from '../lib/flow'

interface AgentData extends Record<string, unknown> {
  id: NodeId
  title: string
  role: string
  state: NodeState
  note: string
  badge?: string
  selected: boolean
}
type AgentNode = Node<AgentData, 'agent'>

const RING: Record<NodeState, string> = {
  idle: 'border-slate-300 bg-white',
  running: 'border-amber-400 bg-amber-50 shadow-[0_0_0_4px_rgba(251,191,36,0.25)]',
  done: 'border-teal-500 bg-teal-50',
  failed: 'border-coral-500 bg-coral-50',
}
const DOT: Record<NodeState, string> = {
  idle: 'bg-slate-300',
  running: 'bg-amber-400 animate-pulse',
  done: 'bg-teal-500',
  failed: 'bg-coral-500',
}

function AgentCard({ data }: NodeProps<AgentNode>) {
  const sides = [Position.Top, Position.Bottom, Position.Left, Position.Right]
  return (
    <div
      className={`w-52 cursor-pointer rounded-xl border-2 px-3.5 py-2.5 transition-all ${RING[data.state]} ${
        data.selected ? 'ring-2 ring-slate-900/70 ring-offset-2' : ''
      }`}
    >
      {sides.map((p) => (
        <Handle key={p} id={p} type="source" position={p} className="!h-1.5 !w-1.5 !border-0 !bg-slate-300" />
      ))}
      <div className="flex items-center gap-2">
        <span className={`h-2.5 w-2.5 rounded-full ${DOT[data.state]}`} />
        <span className="text-sm font-semibold">{data.title}</span>
        {data.badge && (
          <span className="ml-auto rounded-full bg-coral-100 px-2 py-0.5 text-[11px] font-medium text-coral-700">
            {data.badge}
          </span>
        )}
      </div>
      <div className="mt-0.5 text-[11px] uppercase tracking-wide text-slate-400">{data.role}</div>
      <div className="mt-1 truncate text-xs text-slate-600" title={data.note}>
        {data.note}
      </div>
    </div>
  )
}

const nodeTypes = { agent: AgentCard }

// Nodes are 208px wide; columns sit 340px apart so edges and labels have room between them.
const LAYOUT: Record<NodeId, { x: number; y: number; title: string; role: string }> = {
  intake: { x: 0, y: 0, title: 'Intake chat', role: 'external' },
  reviewer: { x: 680, y: 0, title: 'Human reviewer', role: 'decides' },
  chief: { x: 340, y: 150, title: 'Chief', role: 'code state machine' },
  extraction: { x: 0, y: 320, title: 'Extraction', role: 'agent' },
  underwriter: { x: 340, y: 320, title: 'Underwriter', role: 'agent' },
  checker: { x: 680, y: 320, title: 'Checker', role: 'independent agent' },
}

function edgeStyle(active: boolean, done: boolean) {
  return {
    stroke: active ? '#f59e0b' : done ? '#14b8a6' : '#cbd5e1',
    strokeWidth: active ? 2.5 : 2,
  }
}

export default function FlowGraph({
  flow,
  selected,
  onSelect,
}: {
  flow: Flow
  selected: NodeId | null
  onSelect: (id: NodeId | null) => void
}) {
  const nodes = useMemo<AgentNode[]>(
    () =>
      (Object.keys(LAYOUT) as NodeId[]).map((id) => ({
        id,
        type: 'agent',
        position: { x: LAYOUT[id].x, y: LAYOUT[id].y },
        draggable: false,
        data: {
          id,
          title: LAYOUT[id].title,
          role: LAYOUT[id].role,
          state: flow.nodes[id].state,
          note: flow.nodes[id].note,
          selected: selected === id,
          badge: id === 'checker' && flow.retries > 0 ? `retry ${flow.retries}` : undefined,
        },
      })),
    [flow, selected],
  )

  const edges = useMemo<Edge[]>(() => {
    const n = flow.nodes
    const spoke = (id: string, from: NodeId, to: NodeId, sh: string, th: string): Edge => {
      const active = n[from].state === 'running' || n[to].state === 'running'
      const done = n[to].state === 'done' && !active
      return {
        id,
        source: from,
        target: to,
        sourceHandle: sh,
        targetHandle: th,
        type: 'smoothstep',
        animated: n[to].state === 'running' && to !== 'reviewer' && from === 'chief',
        style: edgeStyle(active, done),
        markerEnd: { type: MarkerType.ArrowClosed, color: active ? '#f59e0b' : done ? '#14b8a6' : '#cbd5e1' },
      }
    }
    const retryActive = flow.retries > 0 && (n.underwriter.state === 'running' || n.checker.state === 'running')
    return [
      spoke('intake-chief', 'intake', 'chief', Position.Bottom, Position.Left),
      spoke('chief-extraction', 'chief', 'extraction', Position.Bottom, Position.Top),
      spoke('chief-underwriter', 'chief', 'underwriter', Position.Bottom, Position.Top),
      spoke('chief-checker', 'chief', 'checker', Position.Bottom, Position.Top),
      spoke('chief-reviewer', 'chief', 'reviewer', Position.Right, Position.Bottom),
      {
        id: 'retry',
        source: 'checker',
        target: 'underwriter',
        sourceHandle: Position.Bottom,
        targetHandle: Position.Bottom,
        type: 'smoothstep',
        animated: retryActive,
        label: flow.retries > 0 ? `retry ${flow.retries} of 2 (via chief)` : 'retry loop (via chief)',
        labelStyle: { fontSize: 11, fill: flow.retries > 0 ? '#b23a30' : '#94a3b8' },
        labelBgStyle: { fill: '#f8fafc' },
        style: {
          stroke: flow.retries > 0 ? '#f2665a' : '#cbd5e1',
          strokeWidth: 2,
          strokeDasharray: '6 4',
        },
      },
    ]
  }, [flow])

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      connectionMode={ConnectionMode.Loose}
      fitView
      fitViewOptions={{ padding: 0.12, maxZoom: 1.1 }}
      nodesDraggable={false}
      nodesConnectable={false}
      elementsSelectable={false}
      zoomOnScroll={false}
      panOnDrag={false}
      zoomOnDoubleClick={false}
      proOptions={{ hideAttribution: true }}
      onNodeClick={(_, node) => onSelect(node.id as NodeId)}
      onPaneClick={() => onSelect(null)}
    >
      <Background gap={20} color="#e2e8f0" />
    </ReactFlow>
  )
}
