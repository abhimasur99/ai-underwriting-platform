import { useMemo, useState } from 'react'
import { useMode, useQueue } from '../api/hooks'
import { CallChip, Chip, ModeBadge, StageChip, Button } from '../components/Chips'
import { ago } from '../lib/format'
import { navigate } from '../lib/router'

type Filter = 'all' | 'review' | 'flagged'

const FILTERS: { id: Filter; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'review', label: 'Needs review' },
  { id: 'flagged', label: 'Flagged' },
]

export default function Queue() {
  const { rows, error } = useQueue()
  const mode = useMode()
  const [filter, setFilter] = useState<Filter>('all')
  const [search, setSearch] = useState('')

  const shown = useMemo(() => {
    const q = search.trim().toLowerCase()
    return (rows ?? []).filter((r) => {
      if (filter === 'review' && r.state !== 'NEEDS_REVIEW') return false
      if (filter === 'flagged' && r.flags === 0) return false
      return !q || `${r.deal_id} ${r.name} ${r.stage} ${r.call ?? ''}`.toLowerCase().includes(q)
    })
  }, [rows, filter, search])

  return (
    <div className="mx-auto max-w-6xl px-6 py-8">
      <div className="flex items-end justify-between">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-semibold">Deal queue</h1>
            <ModeBadge mode={mode} />
          </div>
          <p className="mt-1 text-sm text-slate-500">
            Every row is a view over the event log. It updates live.
          </p>
        </div>
        <Button tone="primary" onClick={() => navigate('chat')}>
          New deal (intake chat)
        </Button>
      </div>

      <div className="mt-6 flex flex-wrap items-center gap-2">
        {FILTERS.map((f) => (
          <button
            key={f.id}
            onClick={() => setFilter(f.id)}
            className={`rounded-full px-3 py-1 text-sm ring-1 ring-inset transition-colors ${
              filter === f.id
                ? 'bg-slate-900 text-white ring-slate-900'
                : 'bg-white text-slate-600 ring-slate-300 hover:bg-slate-50'
            }`}
          >
            {f.label}
          </button>
        ))}
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search deals"
          className="ml-auto w-56 rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm outline-none focus:border-teal-600 focus:ring-1 focus:ring-teal-600"
        />
      </div>

      <div className="mt-4 overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
            <tr>
              {['Deal', 'Stage', 'Call', 'Flags', 'Age', 'Owner'].map((h) => (
                <th key={h} className="px-4 py-2.5 font-medium">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {shown.map((r) => (
              <tr
                key={r.deal_id}
                onClick={() => navigate(`deals/${r.deal_id}`)}
                className="cursor-pointer hover:bg-slate-50"
              >
                <td className="px-4 py-3">
                  <div className="font-medium">{r.name || 'Untitled deal'}</div>
                  <div className="text-xs text-slate-500">
                    {r.deal_id} · v{r.deal_version}
                  </div>
                </td>
                <td className="px-4 py-3">
                  <StageChip stage={r.stage} />
                </td>
                <td className="px-4 py-3">
                  <CallChip call={r.call} />
                </td>
                <td className="px-4 py-3">
                  {r.escalation ? (
                    <Chip tone="coral" title="Independent check failed after retries">
                      ⚠ escalated
                    </Chip>
                  ) : r.flags > 0 ? (
                    <Chip tone="amber">{r.flags}</Chip>
                  ) : (
                    <span className="text-slate-400">–</span>
                  )}
                </td>
                <td className="px-4 py-3 text-slate-600">{ago(r.created_at)}</td>
                <td className="px-4 py-3 text-slate-600">{r.owner}</td>
              </tr>
            ))}
            {rows && shown.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-10 text-center text-slate-500">
                  {rows.length === 0
                    ? 'No deals yet. Start one from the intake chat.'
                    : 'No deals match this filter.'}
                </td>
              </tr>
            )}
            {!rows && !error && (
              <tr>
                <td colSpan={6} className="px-4 py-10 text-center text-slate-400">
                  Loading…
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {error && (
        <p className="mt-3 text-sm text-coral-700">
          Could not reach the backend ({error}). Is it running on port 8000?
        </p>
      )}
    </div>
  )
}
