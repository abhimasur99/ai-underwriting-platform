import { describe, expect, it } from 'vitest'
import { deriveFlow, nodeActivity } from './flow'
import { cleanRun, ev, state } from '../test/events'

describe('deriveFlow', () => {
  it('starts idle with nothing in the log', () => {
    const flow = deriveFlow([])
    expect(flow.dealState).toBe('CREATED')
    expect(Object.values(flow.nodes).every((n) => n.state === 'idle')).toBe(true)
  })

  it('shows a finished run: every agent done, the reviewer waiting', () => {
    const flow = deriveFlow(cleanRun())
    expect(flow.nodes.extraction.state).toBe('done')
    expect(flow.nodes.underwriter).toEqual({ state: 'done', note: 'call screen' })
    expect(flow.nodes.checker).toEqual({ state: 'done', note: 'check pass' })
    expect(flow.nodes.chief.state).toBe('done')
    expect(flow.nodes.reviewer).toEqual({ state: 'running', note: 'awaiting you' })
    expect(flow.escalated).toBe(false)
  })

  it('counts a retry and clears the downstream nodes when the underwriter runs again', () => {
    const events = [
      ...cleanRun().slice(0, 13),
      state('CHECKING'),
      ev('handoff.sent', { handoff_id: 'h-3', to: 'checker', task: 'verify' }),
      ev('handoff.returned', { handoff_id: 'h-3', status: 'ok', summary: 'check fail' }, 'checker'),
      ev('check.retry', { retry_count: 1 }),
      state('UNDERWRITING', { retry_count: 1 }),
      ev('handoff.sent', { handoff_id: 'h-4', to: 'underwriter', task: 'size_and_compute' }),
    ]
    const flow = deriveFlow(events)
    expect(flow.retries).toBe(1)
    expect(flow.nodes.underwriter.state).toBe('running')
    expect(flow.nodes.checker.state).toBe('idle')
  })

  it('marks a failed check as failed and an escalation as escalated', () => {
    const events = [
      ...cleanRun().slice(0, 14),
      ev('handoff.sent', { handoff_id: 'h-9', to: 'checker', task: 'verify' }),
      ev('handoff.returned', { handoff_id: 'h-9', status: 'ok', summary: 'check fail' }, 'checker'),
      state('NEEDS_REVIEW', { escalation: true, retry_count: 2 }),
    ]
    const flow = deriveFlow(events)
    expect(flow.nodes.checker.state).toBe('failed')
    expect(flow.escalated).toBe(true)
    expect(flow.nodes.reviewer.note).toBe('check failed: escalated')
  })

  it('shows approval and rejection on the reviewer node', () => {
    expect(deriveFlow([...cleanRun(), state('APPROVED'), state('RELEASED')]).nodes.reviewer)
      .toEqual({ state: 'done', note: 'approved' })
    expect(deriveFlow([...cleanRun(), state('REJECTED')]).nodes.reviewer)
      .toEqual({ state: 'failed', note: 'rejected' })
  })

  it('treats seeded deals (no chat) as submitted once any agent has run', () => {
    const seeded = cleanRun().filter((e) => e.type !== 'deal.submitted' && e.type !== 'file.uploaded')
    expect(deriveFlow(seeded).nodes.intake.state).toBe('done')
  })

  it('shows the deal waiting on the sponsor after the reviewer asks for something', () => {
    const asked = [...cleanRun(), ev('info.requested', { note: 'Send the tax bill' }, 'reviewer'),
      state('NEEDS_INPUT', { awaiting: 'sponsor' })]
    const flow = deriveFlow(asked)
    expect(flow.nodes.reviewer).toEqual({ state: 'running', note: 'waiting on the sponsor' })
    expect(flow.nodes.chief.state).not.toBe('failed')
  })

  it('still shows missing information as a problem when extraction stopped', () => {
    const stopped = [ev('deal.submitted', {}, 'intake'), state('READY'), state('EXTRACTING'),
      state('NEEDS_INPUT', { missing: ['arv'] })]
    expect(deriveFlow(stopped).nodes.chief).toEqual({ state: 'failed', note: 'needs more input' })
  })
})

describe('nodeActivity', () => {
  it('pairs a handoff with its return and keeps tool calls with their agent', () => {
    const events = [...cleanRun(), ev('tool.called', { tool: 'calc.ltc' }, 'underwriter')]
    const under = nodeActivity(events, 'underwriter')
    expect(under.handoffs).toHaveLength(1)
    expect(under.handoffs[0].returned?.payload).toMatchObject({ summary: 'call screen' })
    expect(under.tools).toHaveLength(1)
    expect(nodeActivity(events, 'checker').tools).toHaveLength(0)
  })
})
