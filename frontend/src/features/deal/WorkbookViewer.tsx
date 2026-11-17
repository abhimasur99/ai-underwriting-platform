import { useEffect, useMemo, useState } from 'react'
import { api } from '../../api/client'
import type { WorkbookView } from '../../api/client'
import { cellText } from '../../lib/format'

function letters(n: number): string {
  let out = ''
  while (n > 0) {
    const rem = (n - 1) % 26
    out = String.fromCharCode(65 + rem) + out
    n = Math.floor((n - 1) / 26)
  }
  return out
}

/** Read-only grid of the generated workbook. Formula cells are marked; hover or click shows the
 *  formula, and the value shown is the recalculated one. */
export default function WorkbookViewer({ dealId, bust }: { dealId: string; bust: number | string }) {
  const [book, setBook] = useState<WorkbookView | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [sheet, setSheet] = useState(0)
  const [pinned, setPinned] = useState<{ ref: string; formula: string } | null>(null)

  useEffect(() => {
    api.workbook(dealId).then(
      (b) => {
        setBook(b)
        setError(null)
      },
      (e: Error) => setError(e.message),
    )
  }, [dealId, bust])

  const current = book?.sheets[Math.min(sheet, (book?.sheets.length ?? 1) - 1)]
  const grid = useMemo(() => {
    const map = new Map<string, NonNullable<typeof current>['cells'][number]>()
    current?.cells.forEach((c) => map.set(`${c.row}:${c.col}`, c))
    return map
  }, [current])

  if (error) return <p className="p-6 text-sm text-slate-500">The workbook is not available yet ({error}).</p>
  if (!book || !current) return <p className="p-6 text-sm text-slate-400">Loading workbook…</p>

  const rows = Math.min(current.rows, 120)
  const cols = Math.min(current.cols, 12)
  return (
    <div className="flex h-full flex-col">
      <div className="flex gap-1 border-b border-slate-200 bg-white px-3 pt-2">
        {book.sheets.map((s, i) => (
          <button
            key={s.name}
            onClick={() => {
              setSheet(i)
              setPinned(null)
            }}
            className={`rounded-t-md px-3 py-1.5 text-xs font-medium ${
              i === sheet ? 'bg-slate-100 text-slate-900' : 'text-slate-500 hover:text-slate-800'
            }`}
          >
            {s.name}
          </button>
        ))}
      </div>
      <div className="flex items-center gap-2 border-b border-slate-200 bg-white px-3 py-1.5 text-xs">
        <span className="w-10 font-mono text-slate-500">{pinned?.ref ?? ''}</span>
        <span className="text-slate-400">ƒ</span>
        <code className="truncate text-slate-700">
          {pinned?.formula ?? 'Hover a ƒ cell to see its formula. Read-only.'}
        </code>
      </div>
      <div className="min-h-0 flex-1 overflow-auto bg-white">
        <table className="border-collapse text-xs">
          <thead className="sticky top-0 z-10 bg-slate-100">
            <tr>
              <th className="w-9 border border-slate-200" />
              {Array.from({ length: cols }, (_, i) => (
                <th key={i} className="min-w-28 border border-slate-200 px-2 py-1 font-medium text-slate-500">
                  {letters(i + 1)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {Array.from({ length: rows }, (_, r) => (
              <tr key={r}>
                <td className="sticky left-0 border border-slate-200 bg-slate-100 px-1.5 text-center text-slate-400">
                  {r + 1}
                </td>
                {Array.from({ length: cols }, (_, c) => {
                  const cell = grid.get(`${r + 1}:${c + 1}`)
                  const text = cell ? cellText(cell.value, cell.format) : ''
                  const numeric = cell && typeof cell.value === 'number'
                  return (
                    <td
                      key={c}
                      title={cell?.formula ?? undefined}
                      onMouseEnter={() => cell?.formula && setPinned({ ref: cell.ref, formula: cell.formula })}
                      onClick={() => cell?.formula && setPinned({ ref: cell.ref, formula: cell.formula })}
                      className={`max-w-72 truncate border border-slate-200 px-2 py-1 ${
                        numeric ? 'text-right font-mono' : ''
                      } ${cell?.formula ? 'bg-amber-50/60 underline decoration-amber-400 decoration-dotted' : ''} ${
                        cell?.error ? 'text-coral-600' : ''
                      }`}
                    >
                      {cell?.error ? '#ERR' : text}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
