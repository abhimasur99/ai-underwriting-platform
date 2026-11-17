import { useEffect, useRef, useState } from 'react'
import { api } from '../../api/client'
import type { FileRow, FileText } from '../../api/client'
import { inSpan, parseLocator } from '../../lib/locator'

const LABELS: Record<string, string> = {
  deal_summary: 'Deal summary', purchase_contract: 'Purchase contract', rent_roll: 'Rent roll',
  t12: 'T-12', renovation_budget: 'Renovation budget',
}
const kb = (n: number) => (n < 1024 ? `${n} B` : `${(n / 1024).toFixed(n < 10240 ? 1 : 0)} KB`)

/** The uploaded documents as the platform read them, with the line a number came from
 *  highlighted. Line numbers are the ones every source citation uses. */
export default function FilesTab({
  dealId, files, focus,
}: { dealId: string; files: FileRow[]; focus: { doc: string; locator: string } | null }) {
  const byFocus = focus ? files.find((f) => f.filename === focus.doc) : undefined
  const [picked, setPicked] = useState<string | null>(null)
  const selected = (byFocus && picked === null ? byFocus : files.find((f) => f.file_id === picked)) ?? byFocus ?? files[0]
  const [text, setText] = useState<FileText | null>(null)
  const [error, setError] = useState<string | null>(null)
  const mark = useRef<HTMLLIElement | null>(null)
  const fileId = selected?.file_id
  const span = focus && selected && focus.doc === selected.filename ? parseLocator(focus.locator) : null
  const firstHit = text ? text.lines.findIndex((_, i) => inSpan(span, i + 1)) : -1

  useEffect(() => {
    if (!fileId) return
    let live = true
    api.fileText(dealId, fileId).then(
      (t) => {
        if (live) {
          setText(t)
          setError(null)
        }
      },
      (e: Error) => live && (setText(null), setError(e.message)),
    )
    return () => {
      live = false
    }
  }, [dealId, fileId])

  useEffect(() => {
    mark.current?.scrollIntoView({ block: 'center' })
  }, [text, focus?.locator])

  if (files.length === 0) return <p className="p-8 text-sm text-slate-500">No documents yet.</p>
  return (
    <div className="flex h-full min-h-0">
      <nav aria-label="Documents" className="w-60 shrink-0 overflow-y-auto border-r border-slate-200 bg-paper">
        <ul>
          {files.map((f) => (
            <li key={f.file_id}>
              <button
                onClick={() => setPicked(f.file_id)}
                aria-current={f.file_id === selected?.file_id}
                className={`block w-full border-b border-slate-200 px-4 py-3 text-left hover:bg-white ${
                  f.file_id === selected?.file_id ? 'bg-white' : ''
                }`}
              >
                <span className="block text-sm font-bold">{LABELS[f.label ?? ''] ?? f.label ?? 'Document'}</span>
                <span className="block truncate text-xs text-slate-600">{f.filename}</span>
                <span className="block text-xs text-slate-500">{kb(f.size)}</span>
              </button>
            </li>
          ))}
        </ul>
      </nav>
      <div className="flex min-w-0 flex-1 flex-col bg-white">
        <div className="flex items-center gap-3 border-b border-slate-200 px-4 py-2 text-xs text-slate-600">
          <span className="font-semibold text-ink">{selected?.filename}</span>
          <span>{text?.kind === 'table' ? 'table, header is row 1' : 'text as read by the platform'}</span>
          {span && <span className="ml-auto font-semibold text-ink">Highlighted: the source of the number you opened</span>}
        </div>
        {error ? (
          <p role="alert" className="p-6 text-sm text-coral-700">Could not show this document: {error}</p>
        ) : !text ? (
          <p className="p-6 text-sm text-slate-500">Loading…</p>
        ) : (
          <ol className="min-h-0 flex-1 overflow-auto py-2 font-mono text-xs">
            {text.lines.map((line, i) => {
              const hit = inSpan(span, i + 1)
              return (
                <li key={i} ref={i === firstHit ? mark : undefined}
                  className={`flex gap-3 px-4 py-0.5 ${hit ? 'border-l-4 border-amber-400 bg-amber-50' : 'border-l-4 border-transparent'}`}>
                  <span aria-hidden className="w-8 shrink-0 select-none text-right text-slate-500">{i + 1}</span>
                  <span className="whitespace-pre-wrap break-words">{line || ' '}</span>
                </li>
              )
            })}
          </ol>
        )}
      </div>
    </div>
  )
}
