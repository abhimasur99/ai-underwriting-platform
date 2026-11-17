import { useEffect, useId, useRef } from 'react'
import type { ReactNode } from 'react'

/** The browser's own modal dialog: it traps focus, closes on Escape and restores focus. */
export function Dialog({
  open, onClose, title, children, wide = false,
}: { open: boolean; onClose: () => void; title: string; children: ReactNode; wide?: boolean }) {
  const ref = useRef<HTMLDialogElement>(null)
  const titleId = useId()
  useEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    if (open && !dialog.open) dialog.showModal()
    if (!open && dialog.open) dialog.close()
  }, [open])
  return (
    <dialog
      ref={ref}
      onClose={onClose}
      aria-labelledby={titleId}
      className={`m-auto ${wide ? 'w-[42rem]' : 'w-[30rem]'} max-w-[92vw] border border-ink bg-white p-6 text-ink shadow-xl backdrop:bg-ink/40`}
    >
      <h2 id={titleId} className="text-lg">{title}</h2>
      {open && children}
    </dialog>
  )
}
