import { describe, expect, it } from 'vitest'
import { inSpan, parseLocator } from './locator'

describe('parseLocator', () => {
  it('reads a single line and a row range', () => {
    expect(parseLocator('line 12')).toEqual({ from: 12, to: 12 })
    expect(parseLocator('rows 2-41')).toEqual({ from: 2, to: 41 })
  })
  it('returns null for anything else', () => {
    expect(parseLocator(null)).toBeNull()
    expect(parseLocator('page 3')).toBeNull()
    expect(parseLocator('')).toBeNull()
  })
  it('says whether a line is inside the highlighted span', () => {
    const span = parseLocator('rows 2-4')
    expect([1, 2, 3, 4, 5].map((n) => inSpan(span, n))).toEqual([false, true, true, true, false])
    expect(inSpan(null, 1)).toBe(false)
  })
})
