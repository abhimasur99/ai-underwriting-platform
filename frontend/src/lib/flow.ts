// Turns the event log into what the Flow tab draws. Pure functions: the log is the source of
// truth, so this never keeps state of its own.
import type { ApiEvent } from '../api/client'

export type NodeId = 'intake' | 'chief' | 'extraction' | 'underwriter' | 'checker' | 'reviewer'
export type NodeState = 'idle' | 'running' | 'done' | 'failed'

export interface NodeInfo {
  state: NodeState
  note: string
}

export interface Flow {
  nodes: Record<NodeId, NodeInfo>
  retries: number
  escalated: boolean
  dealState: string
}

const AGENTS: NodeId[] = ['extraction', 'underwriter', 'checker']
const WORKING = ['EXTRACTING', 'EXTRACTED', 'UNDERWRITING', 'UNDERWRITTEN', 'CHECKING', 'CHECKED']

const str = (v: unknown) => (typeof v === 'string' ? v : '')

export function deriveFlow(events: ApiEvent[]): Flow {
  const nodes: Record<NodeId, NodeInfo> = {
    intake: { state: 'idle', note: 'waiting for documents' },
    chief: { state: 'idle', note: 'idle' },
    extraction: { state: 'idle', note: 'idle' },
    underwriter: { state: 'idle', note: 'idle' },
    checker: { state: 'idle', note: 'idle' },
    reviewer: { state: 'idle', note: 'not yet' },
  }
  let dealState = 'CREATED'
  let retries = 0
  let escalated = false
  let submitted = false
  let touched = false
  let asked = false            // the reviewer asked the sponsor for something
  const open = new Map<string, NodeId>()

  const reset = (ids: NodeId[]) =>
    ids.forEach((id) => (nodes[id] = { state: 'idle', note: 'idle' }))

  for (const e of events) {
    const p = e.payload as Record<string, unknown>
    switch (e.type) {
      case 'file.uploaded':
      case 'fact.recorded':
        touched = true
        break
      case 'deal.submitted':
        submitted = true
        break
      case 'state.changed': {
        dealState = str(p.to)
        if (dealState !== 'NEEDS_INPUT') asked = false
        if (typeof p.retry_count === 'number') retries = p.retry_count
        if ('escalation' in p) escalated = Boolean(p.escalation)
        if (dealState === 'EXTRACTING') reset(['extraction', 'underwriter', 'checker', 'reviewer'])
        break
      }
      case 'version.created':
        retries = 0
        escalated = false
        reset(['underwriter', 'checker', 'reviewer'])
        break
      case 'handoff.sent': {
        const to = str(p.to) as NodeId
        if (!AGENTS.includes(to)) break
        open.set(str(p.handoff_id), to)
        nodes[to] = { state: 'running', note: str(p.task) }
        if (to === 'underwriter') reset(['checker', 'reviewer'])
        break
      }
      case 'handoff.returned': {
        const to = open.get(str(p.handoff_id))
        if (!to) break
        open.delete(str(p.handoff_id))
        const summary = str(p.summary)
        const bad = p.status !== 'ok' || /check fail/.test(summary)
        nodes[to] = { state: bad ? 'failed' : 'done', note: summary || str(p.status) }
        break
      }
      case 'review.requested':
        escalated = Boolean(p.escalation)
        break
      case 'info.requested':
        asked = true
        break
      case 'error':
        nodes.chief = { state: 'failed', note: e.summary }
        break
    }
  }

  const running = AGENTS.some((id) => nodes[id].state === 'running')
  // Seeded deals skip the chat, so work having started also proves the package was submitted.
  const started = AGENTS.some((id) => nodes[id].state !== 'idle')
  nodes.intake = submitted || started
    ? { state: 'done', note: 'package submitted' }
    : touched
      ? { state: 'running', note: 'collecting documents' }
      : nodes.intake
  if (nodes.chief.state !== 'failed') {
    if (dealState === 'FAILED') nodes.chief = { state: 'failed', note: 'deal failed' }
    else if (running || WORKING.includes(dealState))
      nodes.chief = { state: 'running', note: 'routing handoffs' }
    else if (['NEEDS_REVIEW', 'APPROVED', 'RELEASED', 'REJECTED'].includes(dealState))
      nodes.chief = { state: 'done', note: 'handed to reviewer' }
    else if (dealState === 'NEEDS_INPUT' && asked)
      nodes.chief = { state: 'idle', note: 'waiting for the sponsor' }
    else if (dealState === 'NEEDS_INPUT')
      nodes.chief = { state: 'failed', note: 'needs more input' }
  }
  if (dealState === 'NEEDS_REVIEW')
    nodes.reviewer = { state: 'running', note: escalated ? 'check failed: escalated' : 'awaiting you' }
  else if (dealState === 'NEEDS_INPUT' && asked)
    nodes.reviewer = { state: 'running', note: 'waiting on the sponsor' }
  else if (dealState === 'APPROVED' || dealState === 'RELEASED')
    nodes.reviewer = { state: 'done', note: 'approved' }
  else if (dealState === 'REJECTED') nodes.reviewer = { state: 'failed', note: 'rejected' }

  return { nodes, retries, escalated, dealState }
}

export interface HandoffRow {
  sent: ApiEvent
  returned?: ApiEvent
}

/** The events a node's drawer shows: its handoffs, its tool calls, and anything else it wrote. */
export function nodeActivity(events: ApiEvent[], node: NodeId) {
  const handoffs: HandoffRow[] = []
  const byId = new Map<string, HandoffRow>()
  const tools: ApiEvent[] = []
  const other: ApiEvent[] = []
  for (const e of events) {
    const p = e.payload as Record<string, unknown>
    if (e.type === 'handoff.sent' && p.to === node) {
      const row = { sent: e }
      handoffs.push(row)
      byId.set(str(p.handoff_id), row)
    } else if (e.type === 'handoff.returned' && byId.has(str(p.handoff_id))) {
      byId.get(str(p.handoff_id))!.returned = e
    } else if (e.type === 'tool.called' && e.actor === node) {
      tools.push(e)
    } else if (belongsTo(e, node)) {
      other.push(e)
    }
  }
  return { handoffs, tools, other }
}

const INTAKE_TYPES = ['deal.created', 'file.uploaded', 'file.classified', 'fact.recorded', 'deal.submitted']
const REVIEWER_TYPES = [
  'review.requested', 'patch.proposed', 'patch.confirmed', 'patch.cancelled', 'override.recorded',
  'decision.recorded', 'memo.rendered', 'version.created',
]

function belongsTo(e: ApiEvent, node: NodeId): boolean {
  if (node === 'intake') return INTAKE_TYPES.includes(e.type)
  if (node === 'reviewer') return REVIEWER_TYPES.includes(e.type)
  if (node === 'chief')
    return ['state.changed', 'check.retry', 'error'].includes(e.type) && e.actor === 'chief'
  return e.actor === node && !['tool.called', 'handoff.returned'].includes(e.type)
}
