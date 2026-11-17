import { useCallback, useState } from 'react'

/** A per-viewer convenience (a panel left open or closed). Storage can be blocked or full, so
 *  every access is guarded and the page works the same without it. */
export function usePersisted(key: string, initial: boolean): [boolean, (value: boolean) => void] {
  const [value, setValue] = useState<boolean>(() => {
    try {
      const stored = window.localStorage.getItem(`bridge.${key}`)
      return stored === null ? initial : stored === '1'
    } catch {
      return initial
    }
  })
  const set = useCallback(
    (next: boolean) => {
      setValue(next)
      try {
        window.localStorage.setItem(`bridge.${key}`, next ? '1' : '0')
      } catch {
        /* the choice just lasts until reload */
      }
    },
    [key],
  )
  return [value, set]
}
