import { describe, expect, it } from 'vitest'
import { nextTab } from './tabs'

const ids = ['memo', 'calculations', 'files', 'process']

describe('nextTab', () => {
  it('moves right and left, wrapping at the ends', () => {
    expect(nextTab(ids, 'memo', 'ArrowRight')).toBe('calculations')
    expect(nextTab(ids, 'process', 'ArrowRight')).toBe('memo')
    expect(nextTab(ids, 'memo', 'ArrowLeft')).toBe('process')
  })
  it('jumps to the first and last with Home and End', () => {
    expect(nextTab(ids, 'files', 'Home')).toBe('memo')
    expect(nextTab(ids, 'files', 'End')).toBe('process')
  })
  it('ignores other keys and unknown tabs', () => {
    expect(nextTab(ids, 'memo', 'Enter')).toBeNull()
    expect(nextTab(ids, 'nope', 'ArrowRight')).toBeNull()
  })
})
