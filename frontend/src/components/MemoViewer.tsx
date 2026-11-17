import { memoUrl, workbookUrl } from '../api/client'

/** The memo is the generated one-page PDF, shown in the browser's own viewer. */
export default function MemoViewer({ dealId, bust }: { dealId: string; bust: number | string }) {
  const src = memoUrl(dealId, bust)
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-4 border-b border-slate-200 bg-white px-4 py-2 text-xs text-slate-500">
        <span>One-page memo (PDF). Sample data; illustrative thresholds.</span>
        <a className="ml-auto text-teal-700 hover:underline" href={src} target="_blank" rel="noreferrer">
          Open in new tab
        </a>
        <a className="text-teal-700 hover:underline" href={workbookUrl(dealId)}>
          Download workbook (.xlsx)
        </a>
      </div>
      <iframe key={String(bust)} title="Memo" src={src} className="min-h-0 flex-1 bg-slate-200" />
    </div>
  )
}
