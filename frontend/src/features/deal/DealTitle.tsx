import { useState } from 'react'
import { api } from '../../api/client'

/** The deal name; click to rename. Enter saves, Escape cancels. */
export default function DealTitle({
  dealId, name, onSaved,
}: { dealId: string; name: string; onSaved: () => void }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(name)
  const [error, setError] = useState<string | null>(null)

  const save = async () => {
    const next = draft.trim()
    if (!next || next === name) {
      setEditing(false)
      setError(null)
      return
    }
    try {
      await api.rename(dealId, next)
      setEditing(false)
      setError(null)
      onSaved()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  if (editing)
    return (
      <div>
        <input
          autoFocus
          value={draft}
          maxLength={80}
          aria-label="Deal name"
          onChange={(e) => setDraft(e.target.value)}
          onBlur={() => void save()}
          onKeyDown={(e) => {
            if (e.key === 'Enter') void save()
            if (e.key === 'Escape') {
              setEditing(false)
              setError(null)
            }
          }}
          className="w-80 border-b border-ink bg-transparent text-[22px] font-bold tracking-tight outline-none"
        />
        {error && <div role="alert" className="text-xs text-coral-700">{error}</div>}
      </div>
    )
  return (
    <button
      onClick={() => {
        setDraft(name)
        setEditing(true)
      }}
      title="Click to rename"
      className="group flex items-baseline gap-2 text-left"
    >
      <h1 className="text-[22px] leading-tight">{name || 'Untitled deal'}</h1>
      <span className="text-xs font-semibold text-slate-500 opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100">
        Rename
      </span>
    </button>
  )
}
