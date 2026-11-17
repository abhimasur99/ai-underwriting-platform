import type { Outcome, VersionDiff } from '../../api/client'
import { mult, pct, usd } from '../../lib/format'
import { CallChip } from '../../ui/Chip'

const SHOW: Record<string, (n: number) => string> = { pct, usd, mult }

function input(path: string, text: string): string {
  const n = Number(text)
  if (text === '' || Number.isNaN(n)) return text
  return path.endsWith('note_rate') ? pct(n) : usd(n)
}

function assumed(kind: string, v: number): string {
  if (kind === 'bps') return `${Math.round(v)} bps`
  return (SHOW[kind] ?? usd)(v)
}

/** Before and after for the version that was just made (or, for a what-if, for the case that was
 *  only tried): the input that moved, the metrics that moved with it, and whether the call
 *  changed. A what-if lists its assumptions instead of inputs and says nothing was saved. */
export default function ChangeCard({ diff, scenario }: { diff: VersionDiff; scenario?: Outcome }) {
  if (!scenario && diff.from_version === diff.to_version) return null
  const flipped = diff.call_before !== diff.call_after
  return (
    <div className="relative mt-2 border border-slate-300 bg-white p-3 text-xs">
      <div className="eyebrow !text-ink">
        {scenario ? 'What-if: not saved' : `Version ${diff.to_version}: what changed`}
      </div>
      {scenario?.assumptions.map((a) => (
        <div key={a.key} className="mt-2">
          <span className="text-slate-600">{a.label}: </span>
          <span className="font-semibold">
            {assumed(a.kind, a.before)} → {assumed(a.kind, a.after)}
          </span>
        </div>
      ))}
      {diff.inputs.map((i) => (
        <div key={i.path} className="mt-2">
          <span className="font-mono">{i.path === 'documents' ? 'documents read again' : i.path}</span>
          {i.path !== 'documents' && (
            <span className="font-semibold">: {input(i.path, i.old)} → {input(i.path, i.new)}</span>
          )}
          {i.reason && <div className="text-slate-600">Reason: {i.reason}</div>}
        </div>
      ))}
      {diff.metrics.length > 0 ? (
        <table className="mt-2 w-full">
          <caption className="sr-only">Metrics that moved</caption>
          <tbody>
            {diff.metrics.map((m) => (
              <tr key={m.key} className="border-t border-slate-100">
                <th scope="row" className="py-1 pr-2 text-left font-normal text-slate-600">{m.label}</th>
                <td className="py-1 text-right font-mono">
                  {SHOW[m.kind](m.before)} → <span className="font-semibold">{SHOW[m.kind](m.after)}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="mt-2 text-slate-600">No calculation moved.</p>
      )}
      <div className="mt-2 flex items-center gap-2 border-t border-slate-100 pt-2">
        {flipped ? (
          <>
            <span>Call moved</span>
            <CallChip call={diff.call_before} /> <span aria-hidden>→</span> <CallChip call={diff.call_after} />
          </>
        ) : (
          <>
            <span className="text-slate-600">Call unchanged</span>
            <CallChip call={diff.call_after} />
          </>
        )}
      </div>
    </div>
  )
}
