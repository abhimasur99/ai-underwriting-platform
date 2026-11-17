import { memoUrl, workbookUrl } from '../../api/client'

/** The memo is the generated one-page PDF, shown in the browser's own viewer. */
export default function MemoViewer({ dealId, bust }: { dealId: string; bust: number | string }) {
  const src = memoUrl(dealId, bust)
  const link = 'whitespace-nowrap font-semibold text-ink underline underline-offset-4'
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-4 border-b border-slate-200 bg-white px-4 py-2 text-xs text-slate-600">
        <span className="truncate" title="Sample data; illustrative thresholds">One-page memo (PDF)</span>
        <a className={`${link} ml-auto`} href={src} target="_blank" rel="noreferrer">Open in new tab</a>
        <a className={link} href={workbookUrl(dealId)}>Download workbook</a>
      </div>
      <iframe key={String(bust)} title="Memo" src={src} className="min-h-0 flex-1 bg-slate-100" />
    </div>
  )
}
