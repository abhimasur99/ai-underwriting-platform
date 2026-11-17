// Previous and next deal needing the reviewer, in queue order. Pure, so it can be tested.
export interface NavRow {
  deal_id: string
  needs_you: boolean
}

export interface Neighbours {
  prev: string | null
  next: string | null
  /** Other deals that need the reviewer (not counting this one). */
  waiting: number
}

export function neighbours(rows: NavRow[] | null, current: string): Neighbours {
  const queue = (rows ?? []).filter((r) => r.needs_you).map((r) => r.deal_id)
  const index = queue.indexOf(current)
  const others = queue.filter((id) => id !== current)
  if (index === -1) return { prev: null, next: others[0] ?? null, waiting: others.length }
  return {
    prev: index > 0 ? queue[index - 1] : null,
    next: index < queue.length - 1 ? queue[index + 1] : null,
    waiting: others.length,
  }
}
