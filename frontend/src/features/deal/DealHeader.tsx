import { useState } from 'react'
import { api } from '../../api/client'
import type { DealDetail } from '../../api/client'
import { workbookUrl } from '../../api/client'
import type { Neighbours } from '../../lib/nav'
import { navigate } from '../../lib/router'
import { Chip } from '../../ui/Chip'
import DealTitle from './DealTitle'
import DecisionActions from './DecisionActions'

const link = 'font-semibold text-slate-600 hover:text-ink'

/** Back and previous on the left, next on the right; the deal's name and where it stands below,
 *  and the decision on the right of that, on every tab. */
export default function DealHeader({
  dealId, detail, nav, onChanged, onRequestInfo, onReply,
}: {
  dealId: string; detail: DealDetail; nav: Neighbours
  onChanged: () => void; onRequestInfo: () => void; onReply: () => void
}) {
  const { status } = detail
  const [error, setError] = useState<string | null>(null)
  const hasResult = !!detail.result

  const archive = async () => {
    setError(null)
    try {
      await api.archive(dealId)
      navigate('')
    } catch (e) {
      setError((e as Error).message)
    }
  }
  const rerun = async () => {
    setError(null)
    try {
      await api.decide(dealId, 'send_back', '')
    } catch (e) {
      setError((e as Error).message)
    }
  }

  return (
    <header className="border-b border-slate-200 bg-paper px-6 py-3">
      <nav aria-label="Deals" className="flex items-center gap-4 text-xs">
        <a href="#/" className={link}>← Deal queue</a>
        {nav.prev && <a href={`#/deals/${nav.prev}`} className={link}>← Previous</a>}
        {nav.next && (
          <a href={`#/deals/${nav.next}`} className={`${link} ml-auto`}>
            Next needing review{nav.waiting > 1 ? ` (${nav.waiting})` : ''} →
          </a>
        )}
      </nav>
      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-2">
        <DealTitle key={status.name} dealId={dealId} name={status.name} onSaved={onChanged} />
        <span className="text-xs text-slate-600">{dealId} · version {status.deal_version}</span>
        <Chip tone={status.needs_you ? 'sky' : 'slate'}>{status.next_action}</Chip>
        <div className="ml-auto flex items-center gap-3">
          <details className="relative">
            <summary className="cursor-pointer list-none border border-slate-300 px-3 py-1.5 text-sm font-semibold text-slate-700 hover:border-ink">
              More
            </summary>
            <ul className="absolute right-0 z-20 mt-1 w-56 border border-ink bg-white py-1 text-sm shadow-xl">
              {hasResult && (
                <li>
                  <a className="block px-3 py-1.5 hover:bg-paper" href={`/api/deals/${dealId}/artifacts/memo.pdf`}
                    target="_blank" rel="noreferrer">Open the memo (PDF)</a>
                </li>
              )}
              {hasResult && (
                <li><a className="block px-3 py-1.5 hover:bg-paper" href={workbookUrl(dealId)}>Download the workbook</a></li>
              )}
              {status.state === 'NEEDS_REVIEW' && (
                <li>
                  <button className="block w-full px-3 py-1.5 text-left hover:bg-paper" onClick={() => void rerun()}>
                    Re-run underwriting and the check
                  </button>
                </li>
              )}
              <li>
                <button className="block w-full px-3 py-1.5 text-left hover:bg-paper" onClick={() => void archive()}
                  title="Hide this deal from the queue. It is kept and can be restored.">
                  Archive this deal
                </button>
              </li>
            </ul>
          </details>
          <DecisionActions dealId={dealId} state={status.state} escalated={status.escalation}
            onRequestInfo={onRequestInfo} onReply={onReply} />
        </div>
      </div>
      {error && <p role="alert" className="mt-1 text-xs text-coral-700">{error}</p>}
    </header>
  )
}
