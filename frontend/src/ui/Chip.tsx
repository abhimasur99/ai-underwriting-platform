import type { ReactNode } from 'react'

type Tone = 'teal' | 'amber' | 'coral' | 'slate' | 'sky'

// Outlined, uppercase, square: status reads as a label, not a pastel pill.
const TONES: Record<Tone, string> = {
  teal: 'border-teal-600/50 text-teal-700',
  amber: 'border-amber-600/50 text-amber-700',
  coral: 'border-coral-600/50 text-coral-700',
  slate: 'border-slate-300 text-slate-500',
  sky: 'border-sky-600/50 text-sky-700',
}

export function Chip({ tone, children, title }: { tone: Tone; children: ReactNode; title?: string }) {
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1 whitespace-nowrap rounded-[2px] border px-2 py-0.5 text-[11px] font-bold uppercase tracking-[0.08em] ${TONES[tone]}`}
    >
      {children}
    </span>
  )
}

export function CallChip({ call }: { call: string | null | undefined }) {
  if (!call) return <span className="text-slate-400">–</span>
  const tone: Tone = call === 'screen' ? 'teal' : call === 'watch' ? 'amber' : 'coral'
  return <Chip tone={tone}>{call}</Chip>
}

export function EscalationBadge() {
  return (
    <Chip tone="coral" title="The independent check kept failing after the retry limit; a human must look">
      Check failed · escalated
    </Chip>
  )
}

/** Shows which mode the backend is in, so nobody mistakes offline fixtures for a live model. */
export function ModeBadge({ mode, onDark = false }: { mode: string | null; onDark?: boolean }) {
  if (!mode) return null
  const live = mode === 'live'
  const base = onDark ? 'border-white/30 text-paper/80' : 'border-slate-300 text-slate-500'
  const liveTone = onDark ? 'border-white/60 text-white' : 'border-sky-600/50 text-sky-700'
  return (
    <span
      title={live ? 'Claude writes the narrative and words the chat. Code computes every number.'
        : 'Offline: cached fixtures and templates. No model is called.'}
      className={`inline-flex items-center gap-1.5 rounded-[2px] border px-2 py-0.5 text-[11px] font-bold uppercase tracking-[0.08em] ${live ? liveTone : base}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${live ? 'bg-current' : 'border border-current'}`} />
      {live ? 'Live model' : 'Offline'}
    </span>
  )
}
