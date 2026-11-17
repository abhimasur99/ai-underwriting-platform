import { useRef } from 'react'
import type { ReactNode } from 'react'
import { nextTab } from '../lib/tabs'

export interface TabSpec {
  id: string
  label: string
}

/** WAI-ARIA tabs: one tab stop, arrows move between tabs, Home and End jump. */
export function Tabs({
  tabs, active, onChange, label, idPrefix,
}: { tabs: readonly TabSpec[]; active: string; onChange: (id: string) => void; label: string; idPrefix: string }) {
  const refs = useRef<Record<string, HTMLButtonElement | null>>({})
  const onKeyDown = (e: React.KeyboardEvent) => {
    const to = nextTab(tabs.map((t) => t.id), active, e.key)
    if (to) {
      e.preventDefault()
      onChange(to)
      refs.current[to]?.focus()
    }
  }
  return (
    <div role="tablist" aria-label={label} onKeyDown={onKeyDown} className="flex gap-6">
      {tabs.map((t) => (
        <button
          key={t.id}
          ref={(el) => {
            refs.current[t.id] = el
          }}
          role="tab"
          id={`${idPrefix}-tab-${t.id}`}
          aria-selected={active === t.id}
          aria-controls={`${idPrefix}-panel-${t.id}`}
          tabIndex={active === t.id ? 0 : -1}
          onClick={() => onChange(t.id)}
          className={`-mb-px border-b-2 px-1 pb-2 text-sm font-semibold transition-colors ${
            active === t.id ? 'border-ink text-ink' : 'border-transparent text-slate-500 hover:text-ink'
          }`}
        >
          {t.label}
        </button>
      ))}
    </div>
  )
}

/** Only the active panel is rendered, so a hidden tab costs nothing and measures nothing. */
export function TabPanel({
  id, active, idPrefix, children,
}: { id: string; active: string; idPrefix: string; children: ReactNode }) {
  if (id !== active) return null
  return (
    <div role="tabpanel" id={`${idPrefix}-panel-${id}`} aria-labelledby={`${idPrefix}-tab-${id}`}
      className="h-full min-h-0">
      {children}
    </div>
  )
}
