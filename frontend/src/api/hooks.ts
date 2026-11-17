import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from './client'
import type { ApiEvent, DealDetail, QueueRow } from './client'

// The server names each SSE frame by event type, and EventSource only delivers named frames to
// listeners registered for that name. This list mirrors docs/data-contracts.md.
const EVENT_TYPES = [
  'deal.created', 'deal.submitted', 'version.created', 'fact.recorded', 'file.uploaded',
  'file.classified', 'checklist.updated', 'state.changed', 'handoff.sent', 'handoff.returned',
  'tool.called', 'extraction.completed', 'underwriting.completed', 'check.completed',
  'check.retry', 'review.requested', 'patch.proposed', 'patch.confirmed', 'patch.cancelled',
  'override.recorded', 'decision.recorded', 'memo.rendered', 'deal.archived',
  'deal.restored', 'deal.renamed', 'info.requested', 'info.replied', 'error',
]

/** Subscribe to an SSE stream and call `onEvent` for every frame. Reconnects on its own. */
export function useStream(url: string | null, onEvent: () => void) {
  const handler = useRef(onEvent)
  useEffect(() => {
    handler.current = onEvent
  })
  useEffect(() => {
    if (!url) return
    const source = new EventSource(url)
    const fire = () => handler.current()
    EVENT_TYPES.forEach((t) => source.addEventListener(t, fire))
    return () => source.close()
  }, [url])
}

/** Run `fn` at most once per `ms`, trailing, so a burst of events causes one refetch. */
export function useDebounced(fn: () => void, ms: number) {
  const timer = useRef<number | undefined>(undefined)
  const latest = useRef(fn)
  useEffect(() => {
    latest.current = fn
  })
  useEffect(() => () => window.clearTimeout(timer.current), [])
  return useCallback(() => {
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => latest.current(), ms)
  }, [ms])
}

/** The whole queue including archived rows; the page filters, so tab counts are exact. */
export function useQueue() {
  const [rows, setRows] = useState<QueueRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const load = useCallback(() => {
    api.queue(true).then(
      (r) => {
        setRows(r)
        setError(null)
      },
      (e: Error) => setError(e.message),
    )
  }, [])
  useEffect(load, [load])
  const refresh = useDebounced(load, 120)
  useStream('/api/stream', refresh)
  return { rows, error, reload: load }
}

/** A deal's detail and full event history, kept live by the deal's event stream. */
export function useDealData(dealId: string) {
  const [detail, setDetail] = useState<DealDetail | null>(null)
  const [events, setEvents] = useState<ApiEvent[]>([])
  const [error, setError] = useState<string | null>(null)
  const last = useRef(0)

  const load = useCallback(() => {
    api.deal(dealId).then(
      (d) => {
        setDetail(d)
        setError(null)
      },
      (e: Error) => setError(e.message),
    )
    api.events(dealId, last.current).then((fresh) => {
      if (!fresh.length) return
      last.current = fresh[fresh.length - 1].event_id
      setEvents((prev) => {
        const seen = new Set(prev.map((e) => e.event_id))
        return [...prev, ...fresh.filter((e) => !seen.has(e.event_id))]
      })
    }, () => undefined)
  }, [dealId])

  // The workspace is keyed by deal id, so a new deal means a fresh hook: no state to reset.
  useEffect(load, [load])

  const refresh = useDebounced(load, 100)
  useStream(`/api/deals/${dealId}/stream`, refresh)
  return { detail, events, error, reload: load }
}

/** "cached" (offline) or "live" (Claude writes the narrative and words the chat). */
export function useMode(): string | null {
  const [mode, setMode] = useState<string | null>(null)
  useEffect(() => {
    api.health().then((h) => setMode(h.mode), () => setMode(null))
  }, [])
  return mode
}
