import type { ReactNode } from 'react'
import { useMode } from '../api/hooks'
import { ModeBadge } from './Chip'

/** Dark top bar shared by every page. `external` is the borrower-facing intake: no internal nav. */
export function TopBar({ active, external = false }: { active?: 'queue' | 'new'; external?: boolean }) {
  const mode = useMode()
  const link = (on: boolean) =>
    `border-b pb-0.5 text-sm font-semibold tracking-wide transition-colors ${
      on ? 'border-paper text-paper' : 'border-transparent text-paper/60 hover:text-paper'
    }`
  return (
    <header className="flex shrink-0 items-center gap-8 bg-ink px-6 py-3.5 text-paper">
      <a href="#/" className="leading-tight">
        <div className="font-display text-[17px] tracking-[0.02em]">Bridge Loan Platform</div>
        <div className="font-display text-[11px] font-light text-paper/60">
          Screening layer · sample data
        </div>
      </a>
      {!external && (
        <nav className="flex items-center gap-6">
          <a href="#/" className={link(active === 'queue')}>Deal queue</a>
          <a href="#/chat" className={link(active === 'new')}>New deal</a>
        </nav>
      )}
      <div className="ml-auto flex items-center gap-4">
        {external && (
          <a href="#/" className="text-sm text-paper/60 hover:text-paper">Internal queue →</a>
        )}
        <ModeBadge mode={mode} onDark />
      </div>
    </header>
  )
}

/** Page frame: top bar, then content filling the rest of the viewport. */
export function Page({
  active, external, children,
}: { active?: 'queue' | 'new'; external?: boolean; children: ReactNode }) {
  return (
    <div className="flex h-full flex-col">
      <TopBar active={active} external={external} />
      <div className="min-h-0 flex-1">{children}</div>
    </div>
  )
}
