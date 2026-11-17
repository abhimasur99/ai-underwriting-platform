// Small builders for event streams used by the unit tests.
import type { ApiEvent } from '../api/client'

let counter = 0

export function ev(
  type: string,
  payload: Record<string, unknown> = {},
  actor = 'chief',
  summary = '',
  version = 1,
): ApiEvent {
  counter += 1
  return {
    event_id: counter,
    deal_id: 'D-0001',
    ts: `2026-11-17T10:00:${String(counter % 60).padStart(2, '0')}Z`,
    actor,
    type,
    summary,
    deal_version: version,
    payload,
  }
}

export const state = (to: string, extra: Record<string, unknown> = {}) =>
  ev('state.changed', { to, ...extra }, 'chief', `-> ${to}`)

/** A clean run from created to waiting for the reviewer. */
export function cleanRun(): ApiEvent[] {
  return [
    ev('deal.created', {}, 'chief'),
    ev('file.uploaded', {}, 'intake', 'rent_roll.csv uploaded'),
    ev('deal.submitted', {}, 'intake'),
    state('READY'),
    ev('handoff.sent', { handoff_id: 'h-1', to: 'extraction', task: 'extract_deal' }),
    state('EXTRACTING'),
    ev('handoff.returned', { handoff_id: 'h-1', status: 'ok', summary: 'extracted' }, 'extraction'),
    state('EXTRACTED'),
    state('UNDERWRITING'),
    ev('handoff.sent', { handoff_id: 'h-2', to: 'underwriter', task: 'size_and_compute' }),
    ev('handoff.returned', { handoff_id: 'h-2', status: 'ok', summary: 'call screen' }, 'underwriter'),
    ev('underwriting.completed', { call: 'screen', flags: 0 }, 'underwriter'),
    state('UNDERWRITTEN'),
    state('CHECKING'),
    ev('handoff.sent', { handoff_id: 'h-3', to: 'checker', task: 'verify' }),
    ev('handoff.returned', { handoff_id: 'h-3', status: 'ok', summary: 'check pass' }, 'checker'),
    ev('check.completed', { status: 'pass' }, 'checker'),
    state('CHECKED'),
    state('NEEDS_REVIEW', { escalation: false }),
    ev('review.requested', { escalation: false }),
  ]
}
