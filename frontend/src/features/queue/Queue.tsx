import { useEffect, useMemo, useState } from 'react'
import { api } from '../../api/client'
import { useQueue } from '../../api/hooks'
import { CallChip, Chip } from '../../ui/Chip'
import { Page } from '../../ui/Shell'
import { ago } from '../../lib/format'
import { navigate } from '../../lib/router'

type Filter = 'all' | 'review' | 'flagged' | 'archived'

const FILTERS: { id: Filter; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'review', label: 'Needs your review' },
  { id: 'flagged', label: 'Flagged' },
  { id: 'archived', label: 'Archived' },
]

interface Notice {
  text: string
  undo?: () => void
  tone?: 'error'
}

export default function Queue() {
  const { rows, error, reload } = useQueue()
  const [filter, setFilter] = useState<Filter>('all')
  const [search, setSearch] = useState('')
  const [picked, setPicked] = useState<Set<string>>(new Set())
  const [notice, setNotice] = useState<Notice | null>(null)

  useEffect(() => {
    if (!notice || notice.tone === 'error') return
    const t = window.setTimeout(() => setNotice(null), 8000)
    return () => window.clearTimeout(t)
  }, [notice])

  const live = useMemo(() => (rows ?? []).filter((r) => !r.archived), [rows])
  const counts: Record<Filter, number> = {
    all: live.length,
    review: live.filter((r) => r.needs_you).length,
    flagged: live.filter((r) => r.flags > 0).length,
    archived: (rows ?? []).length - live.length,
  }

  const shown = useMemo(() => {
    const q = search.trim().toLowerCase()
    const base = filter === 'archived' ? (rows ?? []).filter((r) => r.archived) : live
    return base.filter((r) => {
      if (filter === 'review' && !r.needs_you) return false
      if (filter === 'flagged' && r.flags === 0) return false
      return !q || `${r.deal_id} ${r.name} ${r.next_action} ${r.call ?? ''}`.toLowerCase().includes(q)
    })
  }, [rows, live, filter, search])

  const archivedView = filter === 'archived'
  const ids = shown.map((r) => r.deal_id)
  const selected = ids.filter((id) => picked.has(id))
  const allPicked = ids.length > 0 && selected.length === ids.length

  const toggle = (id: string) =>
    setPicked((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  const change = async (targets: string[], restore: boolean) => {
    const failed: string[] = []
    for (const id of targets) {
      try {
        if (restore) await api.restore(id)
        else await api.archive(id)
      } catch (e) {
        failed.push(`${id}: ${(e as Error).message}`)
      }
    }
    const done = targets.filter((t) => !failed.some((f) => f.startsWith(`${t}:`)))
    setPicked(new Set())
    reload()
    if (failed.length) setNotice({ text: failed.join(' · '), tone: 'error' })
    else
      setNotice({
        text: `${restore ? 'Restored' : 'Archived'} ${done.length === 1 ? done[0] : `${done.length} deals`}.`,
        undo: () => void change(done, !restore),
      })
  }

  return (
    <Page active="queue">
      <div className="h-full overflow-y-auto">
        <section className="bg-ink text-paper">
          <div className="mx-auto flex max-w-6xl items-end justify-between gap-6 px-8 pb-10 pt-12">
            <div>
              <div className="eyebrow !text-paper/50">Internal</div>
              <h1 className="mt-2 text-[44px] leading-[1.05]">Deal queue</h1>
              <p className="mt-3 max-w-lg text-[15px] font-light leading-relaxed text-paper/70">
                The deals that need you come first. Each row says what happens next and who has to
                act. Every row is a view over the event log and updates live.
              </p>
            </div>
            <button
              onClick={() => navigate('chat')}
              className="shrink-0 rounded-[2px] border border-paper px-6 py-2.5 text-sm font-semibold text-paper transition-colors hover:bg-paper hover:text-ink"
            >
              New deal
            </button>
          </div>
        </section>

        <div className="mx-auto max-w-6xl px-8 pb-16 pt-6">
          <div className="flex flex-wrap items-end gap-x-7 gap-y-2 border-b border-slate-200">
            {FILTERS.map((f) => (
              <button
                key={f.id}
                onClick={() => {
                  setFilter(f.id)
                  setPicked(new Set())
                }}
                className={`-mb-px border-b-2 pb-2.5 text-sm font-semibold transition-colors ${
                  filter === f.id
                    ? 'border-ink text-ink'
                    : 'border-transparent text-slate-500 hover:text-ink'
                }`}
              >
                {f.label}
                <span className="ml-1.5 font-normal text-slate-400">{counts[f.id]}</span>
              </button>
            ))}
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search deals"
              aria-label="Search deals"
              className="mb-1.5 ml-auto w-56 border-b border-slate-300 bg-transparent px-1 py-1 text-sm outline-none focus:border-ink"
            />
          </div>

          {selected.length > 0 && (
            <div className="mt-3 flex items-center gap-4 bg-ink px-4 py-2 text-sm text-paper">
              <span>{selected.length} selected</span>
              <button
                onClick={() => void change(selected, archivedView)}
                className="font-semibold underline underline-offset-4 hover:text-white"
              >
                {archivedView ? 'Restore' : 'Archive'} selected
              </button>
              <button onClick={() => setPicked(new Set())} className="ml-auto text-paper/60 hover:text-paper">
                Clear
              </button>
            </div>
          )}

          {notice && (
            <div
              role="status"
              className={`mt-3 flex items-center gap-4 border px-4 py-2 text-sm ${
                notice.tone === 'error'
                  ? 'border-coral-600/50 bg-coral-50 text-coral-700'
                  : 'border-slate-300 bg-white text-slate-700'
              }`}
            >
              <span>{notice.text}</span>
              {notice.undo && (
                <button onClick={notice.undo} className="font-semibold underline underline-offset-4">
                  Undo
                </button>
              )}
              <button onClick={() => setNotice(null)} className="ml-auto text-slate-400 hover:text-ink" aria-label="Dismiss">
                ✕
              </button>
            </div>
          )}

          <table className="mt-3 w-full text-left text-sm">
            <thead>
              <tr className="border-b border-slate-300">
                <th className="w-10 py-2.5 pl-1">
                  <input
                    type="checkbox"
                    aria-label="Select all"
                    checked={allPicked}
                    onChange={() => setPicked(allPicked ? new Set() : new Set(ids))}
                    className="h-3.5 w-3.5 accent-ink"
                  />
                </th>
                {['Deal', 'Next action', 'Call', 'Flags', 'Age', 'Owner', ''].map((h, i) => (
                  <th key={i} className="eyebrow py-2.5 pr-4">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {shown.map((r) => (
                <tr
                  key={r.deal_id}
                  onClick={() => navigate(`deals/${r.deal_id}`)}
                  className={`group cursor-pointer border-b border-slate-200 transition-colors hover:bg-white ${
                    r.archived ? 'opacity-60' : ''
                  }`}
                >
                  <td className="py-3.5 pl-1" onClick={(e) => e.stopPropagation()}>
                    <input
                      type="checkbox"
                      aria-label={`Select ${r.deal_id}`}
                      checked={picked.has(r.deal_id)}
                      onChange={() => toggle(r.deal_id)}
                      className="h-3.5 w-3.5 accent-ink"
                    />
                  </td>
                  <td className="py-3.5 pr-4">
                    <div className="font-bold">{r.name || 'Untitled deal'}</div>
                    <div className="text-xs text-slate-500">
                      {r.deal_id} · v{r.deal_version}
                    </div>
                  </td>
                  <td className="pr-4">
                    {r.needs_you ? (
                      <Chip tone="sky">{r.next_action}</Chip>
                    ) : (
                      <span className="text-slate-700">{r.next_action}</span>
                    )}
                  </td>
                  <td className="pr-4">
                    <CallChip call={r.call} />
                  </td>
                  <td className="pr-4">
                    {r.escalation ? (
                      <Chip tone="coral" title="Independent check failed after retries">
                        Escalated
                      </Chip>
                    ) : r.flags > 0 ? (
                      <Chip tone="amber">
                        {r.flags} {r.flags === 1 ? 'flag' : 'flags'}
                      </Chip>
                    ) : (
                      <span className="text-slate-400">–</span>
                    )}
                  </td>
                  <td className="pr-4 text-slate-600">{ago(r.created_at)}</td>
                  <td className="pr-4 text-slate-600">{r.owner}</td>
                  <td className="pr-1 text-right" onClick={(e) => e.stopPropagation()}>
                    <button
                      onClick={() => void change([r.deal_id], r.archived)}
                      className="text-xs font-semibold text-slate-400 underline-offset-4 hover:text-ink hover:underline group-hover:text-slate-600"
                    >
                      {r.archived ? 'Restore' : 'Archive'}
                    </button>
                  </td>
                </tr>
              ))}
              {rows && shown.length === 0 && (
                <tr>
                  <td colSpan={8} className="py-14 text-center text-slate-500">
                    {archivedView
                      ? 'Nothing archived.'
                      : live.length === 0
                        ? 'No deals yet. Use New deal to start an intake chat.'
                        : 'No deals match this view.'}
                  </td>
                </tr>
              )}
              {!rows && !error && (
                <tr>
                  <td colSpan={8} className="py-14 text-center text-slate-400">
                    Loading…
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          {error && (
            <p className="mt-3 text-sm text-coral-700">
              Could not reach the backend ({error}). Is it running on port 8000?
            </p>
          )}
          <p className="mt-10 text-xs text-slate-400">
            Archiving hides a deal; it is never deleted, because the event log is append-only
            and keeps the audit trail. Restore any time from the Archived tab.
          </p>
        </div>
      </div>
    </Page>
  )
}
