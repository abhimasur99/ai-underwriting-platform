import { useRef, useState } from 'react'
import type { FactView, IntakeStatus } from '../../api/client'

const SLOTS = [
  { label: 'deal_summary', title: 'Deal summary', accepts: 'PDF, Word or text' },
  { label: 'purchase_contract', title: 'Purchase contract', accepts: 'PDF, Word or text' },
  { label: 'rent_roll', title: 'Rent roll', accepts: 'Excel, CSV or PDF' },
  { label: 't12', title: 'T-12 operating statement', accepts: 'Excel, CSV or PDF' },
  { label: 'renovation_budget', title: 'Renovation budget', accepts: 'Excel, CSV or PDF' },
] as const

const MONEY = new Set(['loan_amount_requested', 'purchase_price', 'renovation_budget'])
const money = (v: string) => `$${Number(v).toLocaleString('en-US')}`
const show = (f: FactView) => (MONEY.has(f.key) ? money(f.value) : f.value.replace('_', ' '))

function Slot({
  title, accepts, file, busy, onFile,
}: { title: string; accepts: string; file?: string; busy: boolean; onFile: (f: File) => void }) {
  const picker = useRef<HTMLInputElement>(null)
  const [over, setOver] = useState(false)
  return (
    <li
      onDragOver={(e) => {
        e.preventDefault()
        setOver(true)
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault()
        setOver(false)
        const dropped = e.dataTransfer.files[0]
        if (dropped) onFile(dropped)
      }}
      className={`flex items-center gap-3 border px-3 py-2.5 ${
        over ? 'border-ink bg-white outline outline-2 outline-ink' : 'border-slate-300 bg-white'
      }`}
    >
      <span aria-hidden className={`h-2.5 w-2.5 shrink-0 ${file ? 'bg-teal-600' : 'border border-slate-400'}`} />
      <div className="min-w-0 flex-1">
        <div className="text-sm font-bold">{title}</div>
        <div className="truncate text-xs text-slate-600">
          {file ? `Received: ${file}` : `Drop a file here · ${accepts}`}
        </div>
      </div>
      <input ref={picker} type="file" hidden aria-label={`Choose a file for ${title}`}
        onChange={(e) => {
          const chosen = e.target.files?.[0]
          if (chosen) onFile(chosen)
          e.target.value = ''
        }} />
      <button type="button" disabled={busy} onClick={() => picker.current?.click()}
        className="shrink-0 border border-ink px-2.5 py-1 text-xs font-semibold hover:bg-ink hover:text-paper disabled:border-slate-300 disabled:text-slate-400">
        {file ? 'Replace' : 'Choose'}
      </button>
    </li>
  )
}

/** What has arrived and what was read from it. Dropping a file on a row files it as that document;
 *  dropping on the chat lets the assistant work out which one it is. */
export default function PackagePanel({
  status, busy, onFile,
}: { status: IntakeStatus | null; busy: boolean; onFile: (label: string, file: File) => void }) {
  const files = status?.files ?? {}
  const facts = status?.facts ?? []
  const still = status?.checklist.facts_missing ?? []
  const received = SLOTS.filter((s) => files[s.label]).length
  return (
    <aside aria-label="Your package" className="flex w-[22rem] shrink-0 flex-col gap-5 overflow-y-auto">
      <section>
        <div className="flex items-baseline justify-between">
          <h2 className="eyebrow !text-ink">Documents</h2>
          <span className="text-xs text-slate-600">{received} of {SLOTS.length} received</span>
        </div>
        <ul className="mt-2 space-y-2">
          {SLOTS.map((s) => (
            <Slot key={s.label} title={s.title} accepts={s.accepts} file={files[s.label]} busy={busy}
              onFile={(file) => onFile(s.label, file)} />
          ))}
        </ul>
      </section>
      <section>
        <h2 className="eyebrow !text-ink">Details we read</h2>
        {facts.length === 0 ? (
          <p className="mt-2 text-sm text-slate-600">
            The property details are read from your documents as they arrive. You can also tell
            me in the chat.
          </p>
        ) : (
          <dl className="mt-2 border border-slate-300 bg-white text-sm">
            {facts.map((f) => (
              <div key={f.key} className="border-b border-slate-200 px-3 py-2 last:border-0">
                <dt className="text-xs text-slate-600">{f.label}</dt>
                <dd className="font-semibold">{show(f)}</dd>
                <dd className="text-xs text-slate-500">{f.source}</dd>
              </div>
            ))}
          </dl>
        )}
        {still.length > 0 && facts.length > 0 && (
          <p className="mt-2 text-xs text-slate-600">
            Still needed: {still.map((k) => k.replaceAll('_', ' ')).join(', ')}
          </p>
        )}
      </section>
    </aside>
  )
}
