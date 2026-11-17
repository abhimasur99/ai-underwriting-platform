import type { DealDetail } from '../../api/client'
import { Chip } from '../../ui/Chip'
import { metricValue } from '../../lib/format'

const TONE = { pass: 'teal', watch: 'amber', decline: 'coral' } as const

/** The review: questions for the sponsor (each can be sent with one click), exceptions, and the
 *  metrics that drive the call against their thresholds. */
export default function ReviewPanel({
  detail, onAsk, onHide, showKeyMetrics,
}: {
  detail: DealDetail; onAsk: (prefill: string) => void; onHide: () => void
  showKeyMetrics: boolean         // the Calculations tab already shows them in full
}) {
  const { result } = detail
  if (!result) return null
  const canAsk = detail.status.state === 'NEEDS_REVIEW'
  return (
    <aside aria-label="Review" className="flex w-[19rem] shrink-0 flex-col overflow-y-auto border-l border-slate-200 bg-white">
      <div className="flex items-center border-b border-slate-200 px-4 py-2.5">
        <h2 className="eyebrow !text-ink">Review</h2>
        <button onClick={onHide} className="ml-auto text-xs font-semibold text-slate-500 hover:text-ink">
          Hide
        </button>
      </div>
      <div className="space-y-5 p-4 text-sm">
        <section>
          <h3 className="eyebrow">Questions for the sponsor</h3>
          {result.open_questions.length === 0 ? (
            <p className="mt-1 text-slate-500">None.</p>
          ) : (
            <ul className="mt-2 space-y-3">
              {result.open_questions.map((q) => (
                <li key={q} className="leading-snug">
                  {q}
                  {canAsk && (
                    <button onClick={() => onAsk(q)}
                      className="mt-1 block text-xs font-semibold text-ink underline underline-offset-4">
                      Ask the sponsor
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>
        {result.flags.length > 0 && (
          <section>
            <h3 className="eyebrow">Exceptions</h3>
            <ul className="mt-2 space-y-2">
              {result.flags.map((f) => (
                <li key={`${f.code}-${f.field ?? ''}`} className="leading-snug">
                  <span className="font-mono text-xs font-semibold">{f.code}</span>
                  <span className="block text-slate-600">{f.message}</span>
                </li>
              ))}
            </ul>
          </section>
        )}
        {showKeyMetrics && (
        <section>
          <h3 className="eyebrow">Key metrics</h3>
          <table className="mt-2 w-full text-xs">
            <tbody>
              {result.rule_checks.map((c) => (
                <tr key={c.metric} className="border-t border-slate-100">
                  <th scope="row" className="py-1.5 pr-2 text-left font-normal text-slate-600">{c.label}</th>
                  <td className="py-1.5 pr-2 text-right font-mono">{metricValue(c.metric, c.value)}</td>
                  <td className="py-1.5 text-right"><Chip tone={TONE[c.status]}>{c.status}</Chip></td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
        )}
      </div>
    </aside>
  )
}
