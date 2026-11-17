import type { ReactNode } from 'react'

type Tone = 'teal' | 'amber' | 'coral' | 'slate' | 'sky'

const TONES: Record<Tone, string> = {
  teal: 'bg-teal-50 text-teal-700 ring-teal-600/20',
  amber: 'bg-amber-50 text-amber-800 ring-amber-600/25',
  coral: 'bg-coral-50 text-coral-700 ring-coral-600/25',
  slate: 'bg-slate-100 text-slate-600 ring-slate-500/15',
  sky: 'bg-sky-50 text-sky-700 ring-sky-600/20',
}

export function Chip({ tone, children, title }: { tone: Tone; children: ReactNode; title?: string }) {
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${TONES[tone]}`}
    >
      {children}
    </span>
  )
}

export function CallChip({ call }: { call: string | null | undefined }) {
  if (!call) return <span className="text-slate-400">–</span>
  const tone: Tone = call === 'screen' ? 'teal' : call === 'watch' ? 'amber' : 'coral'
  return <Chip tone={tone}>{call.charAt(0).toUpperCase() + call.slice(1)}</Chip>
}

const STATE_TONE: Record<string, Tone> = {
  CREATED: 'slate',
  AWAITING_DOCS: 'slate',
  READY: 'slate',
  NEEDS_INPUT: 'amber',
  EXTRACTING: 'amber',
  EXTRACTED: 'amber',
  UNDERWRITING: 'amber',
  UNDERWRITTEN: 'amber',
  CHECKING: 'amber',
  CHECKED: 'amber',
  SENT_BACK: 'amber',
  NEEDS_REVIEW: 'sky',
  APPROVED: 'teal',
  RELEASED: 'teal',
  REJECTED: 'coral',
  FAILED: 'coral',
}

export function StateChip({ state }: { state: string }) {
  return <Chip tone={STATE_TONE[state] ?? 'slate'}>{state.replaceAll('_', ' ').toLowerCase()}</Chip>
}

export function StageChip({ stage }: { stage: string }) {
  const tone: Tone =
    stage === 'Done' ? 'teal' : stage === 'Failed' ? 'coral' : stage === 'Review' ? 'sky'
      : stage === 'Awaiting docs' ? 'slate' : 'amber'
  return <Chip tone={tone}>{stage}</Chip>
}

export function EscalationBadge() {
  return (
    <Chip tone="coral" title="The independent check kept failing after the retry limit; a human must look">
      ⚠ check failed: escalated
    </Chip>
  )
}

export function Button({
  children,
  onClick,
  tone = 'slate',
  disabled,
  title,
  type = 'button',
}: {
  children: ReactNode
  onClick?: () => void
  tone?: 'primary' | 'slate' | 'danger'
  disabled?: boolean
  title?: string
  type?: 'button' | 'submit'
}) {
  const styles = {
    primary: 'bg-teal-600 text-white hover:bg-teal-700 disabled:bg-teal-600/40',
    danger: 'bg-white text-coral-700 ring-1 ring-coral-200 hover:bg-coral-50 disabled:text-coral-700/40',
    slate: 'bg-white text-slate-700 ring-1 ring-slate-300 hover:bg-slate-50 disabled:text-slate-400',
  }[tone]
  return (
    <button
      type={type}
      title={title}
      disabled={disabled}
      onClick={onClick}
      className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors disabled:cursor-not-allowed ${styles}`}
    >
      {children}
    </button>
  )
}
