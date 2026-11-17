// A readable account of a deal for the Process tab: what happened, in plain words, without the
// state-machine bookkeeping. The raw events stay available behind a toggle. Pure functions.
import type { ApiEvent } from '../api/client'

export type Tone = 'normal' | 'good' | 'warn' | 'bad'

export interface LogEntry {
  id: number
  ts: string
  who: string
  text: string
  tone: Tone
}

const TASKS: Record<string, string> = {
  extract_deal: 'read the documents',
  size_and_compute: 'size the loan and compute the metrics',
  verify: 'check the numbers independently',
}
const AGENTS: Record<string, string> = {
  extraction: 'Extraction', underwriter: 'Underwriter', checker: 'Checker',
}
const DECISIONS: Record<string, string> = {
  approve: 'approved the deal', reject: 'rejected the deal', send_back: 're-ran the deal',
  request_info: 'asked the sponsor for more information',
}

const str = (v: unknown): string => (typeof v === 'string' ? v : '')
const num = (v: unknown): string => (typeof v === 'number' ? String(v) : '')

function describe(e: ApiEvent): Omit<LogEntry, 'id' | 'ts'> | null {
  const p = e.payload as Record<string, unknown>
  const entry = (who: string, text: string, tone: Tone = 'normal') => ({ who, text, tone })
  switch (e.type) {
    case 'deal.created':
      return entry('Chief', 'Deal created')
    case 'file.uploaded':
      return entry('Sponsor', e.summary.replace(/ uploaded$/, '') + ' received')
    case 'deal.submitted':
      return entry('Intake', 'Package complete, sent for processing')
    case 'handoff.sent': {
      const to = AGENTS[str(p.to)] ?? str(p.to)
      return entry('Chief', `Asked ${to} to ${TASKS[str(p.task)] ?? str(p.task)}`)
    }
    case 'extraction.completed':
      return entry('Extraction', 'Documents read')
    case 'underwriting.completed':
      return entry('Underwriter', `Underwriting finished: call ${str(p.call) || 'unknown'}`)
    case 'check.completed': {
      const status = str(p.status)
      if (p.scope === 'memo_number_match') return entry('Checker', `Memo re-checked: ${status}`)
      return entry('Checker', `Independent check: ${status}`,
        status === 'pass' ? 'good' : status === 'warn' ? 'warn' : 'bad')
    }
    case 'check.retry':
      return entry('Chief', `The check disagreed, trying again (${num(p.retry_count)} of 2)`, 'warn')
    case 'review.requested':
      return p.escalation
        ? entry('Chief', 'The check kept failing: escalated to you', 'bad')
        : entry('Chief', 'Ready for your review', 'good')
    case 'version.created':
      return entry('Chief', `Deal version ${num(p.to)} created`)
    case 'patch.proposed':
      return entry('Chief', `Edit proposed: ${e.summary}`)
    case 'patch.confirmed':
      return entry('You', `Edit applied: ${str(p.path)}`)
    case 'patch.cancelled':
      return entry('You', 'Edit cancelled')
    case 'override.recorded':
      return entry('You', e.summary)
    case 'memo.rendered':
      return entry('Chief', 'Memo updated')
    case 'decision.recorded': {
      const note = str(p.rationale)
      return entry('You', `${DECISIONS[str(p.decision)] ?? str(p.decision)}${note ? `: ${note}` : ''}`,
        p.decision === 'approve' ? 'good' : p.decision === 'reject' ? 'bad' : 'normal')
    }
    case 'info.requested':
      return entry('You', `Asked the sponsor: ${str(p.note)}`)
    case 'info.replied': {
      const files = Array.isArray(p.files) ? (p.files as string[]) : []
      const said = str(p.text)
      const sent = files.length ? `sent ${files.join(', ')}` : ''
      return entry('Sponsor', `Replied${said ? `: ${said}` : ''}${said && sent ? ' and ' : sent ? ': ' : ''}${sent}`)
    }
    case 'deal.archived':
    case 'deal.restored':
    case 'deal.renamed':
      return entry('You', e.summary)
    case 'error':
      return entry('Chief', `Error: ${e.summary}`, 'bad')
    default:
      return null          // state changes, tool calls, checklist updates: detail for the log toggle
  }
}

/** Oldest first. */
export function readableLog(events: ApiEvent[]): LogEntry[] {
  const out: LogEntry[] = []
  for (const e of events) {
    const d = describe(e)
    if (d) out.push({ id: e.event_id, ts: e.ts, ...d })
  }
  return out
}
