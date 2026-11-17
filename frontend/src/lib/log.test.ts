import { describe, expect, it } from 'vitest'
import { readableLog } from './log'
import { cleanRun, ev } from '../test/events'

describe('readableLog', () => {
  it('turns a clean run into a short story without state-machine lines', () => {
    const lines = readableLog(cleanRun()).map((l) => l.text)
    expect(lines).toEqual([
      'Deal created',
      'rent_roll.csv received',
      'Package complete, sent for processing',
      'Asked Extraction to read the documents',
      'Asked Underwriter to size the loan and compute the metrics',
      'Underwriting finished: call screen',
      'Asked Checker to check the numbers independently',
      'Independent check: pass',
      'Ready for your review',
    ])
  })

  it('never shows raw transitions, tool calls or checklist updates', () => {
    const noisy = [
      ev('state.changed', { to: 'CHECKED' }), ev('tool.called', {}, 'checker'),
      ev('checklist.updated'), ev('file.classified'), ev('fact.recorded'),
    ]
    expect(readableLog(noisy)).toEqual([])
  })

  it('marks a failed check, a retry and an escalation', () => {
    const lines = readableLog([
      ev('check.completed', { status: 'fail' }, 'checker'),
      ev('check.retry', { retry_count: 1 }),
      ev('review.requested', { escalation: true }),
    ])
    expect(lines.map((l) => l.tone)).toEqual(['bad', 'warn', 'bad'])
    expect(lines[1].text).toBe('The check disagreed, trying again (1 of 2)')
    expect(lines[2].text).toBe('The check kept failing: escalated to you')
  })

  it('records the reply to the broker as drafted, edited and approved, never as sent', () => {
    const lines = readableLog([ev('reply.drafted', {}, 'chief'), ev('reply.edited', {}), ev('reply.approved', {})])
    expect(lines.map((l) => l.text)).toEqual([
      'Drafted the reply to the broker (not sent)',
      'Edited the reply to the broker',
      'Approved the reply to the broker (not sent)',
    ])
  })

  it('tells decisions and the request-info conversation in the reviewer’s own terms', () => {
    const lines = readableLog([
      ev('info.requested', { note: 'Send the tax bill' }),
      ev('info.replied', { text: 'Attached.', files: ['tax.pdf'] }, 'intake'),
      ev('info.replied', { text: '', files: ['tax.pdf', 'lease.pdf'] }, 'intake'),
      ev('info.replied', { text: 'Yes.', files: [] }, 'intake'),
      ev('decision.recorded', { decision: 'approve', rationale: 'Clean exit' }),
      ev('decision.recorded', { decision: 'reject', rationale: '' }),
    ])
    expect(lines.map((l) => l.text)).toEqual([
      'Asked the sponsor: Send the tax bill',
      'Replied: Attached. and sent tax.pdf',
      'Replied: sent tax.pdf, lease.pdf',
      'Replied: Yes.',
      'approved the deal: Clean exit',
      'rejected the deal',
    ])
    expect(lines.at(-2)?.tone).toBe('good')
    expect(lines.at(-1)?.tone).toBe('bad')
  })

  it('keeps the oldest event first and keeps event ids for stable list keys', () => {
    const events = cleanRun()
    const lines = readableLog(events)
    expect(lines.map((l) => l.id)).toEqual([...lines.map((l) => l.id)].sort((a, b) => a - b))
  })
})
