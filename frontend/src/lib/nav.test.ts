import { describe, expect, it } from 'vitest'
import { neighbours } from './nav'

const rows = [
  { deal_id: 'D-0001', needs_you: true },
  { deal_id: 'D-0002', needs_you: false },
  { deal_id: 'D-0003', needs_you: true },
  { deal_id: 'D-0004', needs_you: true },
]

describe('neighbours', () => {
  it('walks the deals that need the reviewer, skipping the rest', () => {
    expect(neighbours(rows, 'D-0003')).toEqual({ prev: 'D-0001', next: 'D-0004', waiting: 2 })
  })

  it('has no previous on the first and no next on the last', () => {
    expect(neighbours(rows, 'D-0001').prev).toBeNull()
    expect(neighbours(rows, 'D-0004').next).toBeNull()
  })

  it('offers the first waiting deal from a deal that is not waiting itself', () => {
    expect(neighbours(rows, 'D-0002')).toEqual({ prev: null, next: 'D-0001', waiting: 3 })
  })

  it('is empty when nothing needs the reviewer, or before the queue loads', () => {
    expect(neighbours([{ deal_id: 'D-0001', needs_you: false }], 'D-0001')).toEqual({
      prev: null, next: null, waiting: 0,
    })
    expect(neighbours(null, 'D-0001')).toEqual({ prev: null, next: null, waiting: 0 })
  })
})
