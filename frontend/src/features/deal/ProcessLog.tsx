import { useState } from 'react'
import type { ApiEvent } from '../../api/client'
import { clock } from '../../lib/format'
import { readableLog } from '../../lib/log'
import type { Tone } from '../../lib/log'

const TONE: Record<Tone, string> = {
  normal: 'text-slate-700', good: 'text-teal-700', warn: 'text-amber-700', bad: 'text-coral-700',
}

/** What happened, in plain words, newest first. The raw event log is one toggle away. */
export default function ProcessLog({ events }: { events: ApiEvent[] }) {
  const [raw, setRaw] = useState(false)
  const entries = readableLog(events).reverse()
  return (
    <section aria-label="Deal history" className="flex h-full min-h-0 flex-col">
      <div className="flex items-center border-b border-slate-200 px-4 py-2.5">
        <h2 className="eyebrow !text-ink">{raw ? 'Raw event log' : 'What happened'}</h2>
        <button onClick={() => setRaw(!raw)} aria-pressed={raw}
          className="ml-auto text-xs font-semibold text-slate-500 underline underline-offset-4 hover:text-ink">
          {raw ? 'Show the summary' : 'Show raw events'}
        </button>
      </div>
      <ul className="min-h-0 flex-1 space-y-2 overflow-y-auto p-4 text-xs">
        {raw
          ? [...events].reverse().map((e) => (
              <li key={e.event_id} className="flex gap-2 font-mono">
                <span className="shrink-0 whitespace-nowrap text-slate-500">{clock(e.ts)}</span>
                <span className="shrink-0 text-slate-600">{e.actor}</span>
                <span className="break-words text-slate-700">{e.type}: {e.summary}</span>
              </li>
            ))
          : entries.map((l) => (
              <li key={l.id} className="flex gap-3">
                <span className="w-[5.5rem] shrink-0 whitespace-nowrap text-slate-500">{clock(l.ts)}</span>
                <span className={TONE[l.tone]}>
                  <span className="font-semibold">{l.who}</span> {l.text}
                </span>
              </li>
            ))}
        {!raw && entries.length === 0 && <li className="text-slate-500">Nothing has happened yet.</li>}
      </ul>
    </section>
  )
}
