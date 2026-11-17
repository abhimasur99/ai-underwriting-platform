import type { ReactNode } from 'react'

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
    primary: 'border-ink bg-ink text-paper hover:bg-slate-700 hover:border-slate-700',
    slate: 'border-ink text-ink hover:bg-ink hover:text-paper',
    danger: 'border-coral-600 text-coral-700 hover:bg-coral-600 hover:text-white',
  }[tone]
  return (
    <button
      type={type}
      title={title}
      disabled={disabled}
      onClick={onClick}
      className={`rounded-[2px] border px-4 py-1.5 text-sm font-semibold transition-colors disabled:cursor-not-allowed disabled:border-slate-300 disabled:bg-transparent disabled:text-slate-400 ${styles}`}
    >
      {children}
    </button>
  )
}
