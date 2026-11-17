import { describe, expect, it } from 'vitest'
import { resolveTab } from './dealTabs'

describe('resolveTab', () => {
  it('opens the memo once there is a result, and the process view while it runs', () => {
    expect(resolveTab(undefined, true)).toBe('memo')
    expect(resolveTab(undefined, false)).toBe('process')
  })
  it('keeps old links working', () => {
    expect(resolveTab('review', true)).toBe('memo')
    expect(resolveTab('flow', true)).toBe('process')
    expect(resolveTab('numbers', true)).toBe('calculations')
  })
  it('falls back to the process view when a tab needs a result that does not exist yet', () => {
    expect(resolveTab('memo', false)).toBe('process')
    expect(resolveTab('calculations', false)).toBe('process')
    expect(resolveTab('files', false)).toBe('files')
  })
  it('ignores a tab name it does not know', () => {
    expect(resolveTab('nonsense', true)).toBe('memo')
  })
})
