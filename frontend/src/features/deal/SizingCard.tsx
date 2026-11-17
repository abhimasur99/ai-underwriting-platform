import type { Sizing } from '../../api/client'
import { usd } from '../../lib/format'
import { CallChip } from '../../ui/Chip'

/** The largest loan that still reaches the target call, next to the loan as requested. Nothing is
 *  saved: the figure comes from re-running the same underwriting at different loan sizes. */
export default function SizingCard({ sizing }: { sizing: Sizing }) {
  const goal = sizing.target === 'watch' ? 'avoid a decline' : 'screen'
  return (
    <div className="relative mt-2 border border-slate-300 bg-white p-3 text-xs">
      <div className="eyebrow !text-ink">Largest loan that would {goal}: not saved</div>
      <table className="mt-2 w-full">
        <caption className="sr-only">Requested loan against the largest loan that works</caption>
        <tbody>
          <tr className="border-t border-slate-100">
            <th scope="row" className="py-1 pr-2 text-left font-normal text-slate-600">Requested loan</th>
            <td className="py-1 text-right font-mono">{usd(sizing.current_loan)}</td>
          </tr>
          <tr className="border-t border-slate-100">
            <th scope="row" className="py-1 pr-2 text-left font-normal text-slate-600">Largest loan</th>
            <td className="py-1 text-right font-mono font-semibold">
              {sizing.max_loan == null ? 'None in the program range' : usd(sizing.max_loan)}
            </td>
          </tr>
        </tbody>
      </table>
      <div className="mt-2 flex items-center gap-2 border-t border-slate-100 pt-2">
        <span className="text-slate-600">Call as requested</span>
        <CallChip call={sizing.current_call} />
        {sizing.call_at_max && (
          <>
            <span aria-hidden>→</span>
            <span className="text-slate-600">at the largest loan</span>
            <CallChip call={sizing.call_at_max} />
          </>
        )}
      </div>
    </div>
  )
}
