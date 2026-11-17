import { useState } from 'react'
import type { ApiEvent, Deal, UnderwritingResult, CheckReport } from '../../api/client'
import { LABELS, metricValue, mult, pct, usd } from '../../lib/format'
import { sourceFor, toolCallFor } from '../../lib/metrics'
import { CallChip, Chip } from '../../ui/Chip'

const tone = (s: string) => (s === 'pass' ? 'teal' : s === 'watch' || s === 'warn' ? 'amber' : 'coral')

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-500">{title}</h3>
      {children}
    </section>
  )
}

// A reason code like LTC_DECLINE or REFI_CUSHION_NEGATIVE_BASE -> show its numbers in that unit.
const REASON_KEYS = [
  'ltc', 'ltv_as_is', 'loan_to_arv', 'exit_dscr', 'implied_cap_rate', 'rent_roll_vs_t12',
  'sources_vs_uses', 'refi_cushion',
]
function reasonValue(code: string, v: number | null | undefined): string {
  if (v == null) return '–'
  const lower = code.toLowerCase()
  const key = REASON_KEYS.find((k) => lower.startsWith(k))
  return key ? metricValue(key, v) : String(v)
}

function val(v: unknown): string {
  if (typeof v === 'number') return Number.isInteger(v) ? v.toLocaleString('en-US') : String(+v.toPrecision(7))
  return v == null ? '–' : String(v)
}

/** One metric. Click to see the formula, its inputs, and the document line each input came from. */
function MetricRow({
  k, value, result, deal, events, onViewSource,
}: {
  k: string; value: number; result: UnderwritingResult; deal: Deal; events: ApiEvent[]
  onViewSource: (doc: string, locator: string) => void
}) {
  const [open, setOpen] = useState(false)
  const e = toolCallFor(k, events, result.deal_version)
  const p = (e?.payload ?? {}) as { formula?: string; inputs?: Record<string, unknown> }
  const check = result.rule_checks.find((c) => c.metric === k)
  return (
    <div className="border-b border-slate-100 last:border-0">
      <button onClick={() => setOpen(!open)} className="flex w-full items-center gap-3 py-2 text-left text-sm hover:bg-slate-50">
        <span className="w-4 text-slate-400">{open ? '▾' : '▸'}</span>
        <span className="flex-1">{LABELS[k] ?? k}</span>
        <span className="font-mono font-medium">{metricValue(k, value)}</span>
        {check ? <Chip tone={tone(check.status)}>{check.status}</Chip> : <span className="w-14" />}
      </button>
      {open && (
        <div className="mb-3 ml-7 space-y-2 rounded-md bg-slate-50 p-3 text-xs">
          {p.formula ? (
            <div>
              <span className="text-slate-400">formula </span>
              <code className="rounded bg-white px-1.5 py-0.5 ring-1 ring-slate-200">{p.formula}</code>
            </div>
          ) : (
            <div className="text-slate-500">No tool record for this metric in the log.</div>
          )}
          {check && (
            <div className="text-slate-600">
              thresholds: watch {check.direction === 'above' ? '>' : '<'}{' '}
              {check.watch_threshold == null ? '–' : metricValue(k, check.watch_threshold)} · decline{' '}
              {check.direction === 'above' ? '>' : '<'}{' '}
              {check.decline_threshold == null ? '–' : metricValue(k, check.decline_threshold)}
            </div>
          )}
          {Object.entries(p.inputs ?? {}).map(([name, v]) => {
            const src = sourceFor(deal, name)
            return (
              <div key={name} className="rounded border border-slate-200 bg-white p-2">
                <div className="font-mono">
                  {name} = <span className="font-semibold">{val(v).slice(0, 120)}</span>
                </div>
                {src && (
                  <div className="mt-1 text-slate-500">
                    {src.kind === 'document' ? (
                      <>
                        {src.doc}, {src.locator}
                        {src.quote && <div className="italic">“{src.quote}”</div>}
                        {src.locator && (
                          <button onClick={() => onViewSource(src.doc ?? '', src.locator ?? '')}
                            className="mt-1 font-semibold text-ink underline underline-offset-4">
                            View in the document
                          </button>
                        )}
                      </>
                    ) : (
                      <>{src.kind}</>
                    )}
                    <div>confidence {(src.confidence * 100).toFixed(0)}%</div>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

function ExitTable({ result }: { result: UnderwritingResult }) {
  const rows: [string, string, string][] = [
    ['NOI', usd(result.exit.noi), usd(result.stress.noi)],
    ['Take-out rate', pct(result.exit.rate), pct(result.stress.rate)],
    ['DSCR cap', usd(result.exit.caps.dscr), usd(result.stress.caps.dscr)],
    ['LTV cap', usd(result.exit.caps.ltv), usd(result.stress.caps.ltv)],
    ['Debt yield cap', usd(result.exit.caps.debt_yield), usd(result.stress.caps.debt_yield)],
    ['Binding cap', result.exit.binding.replace('_', ' '), result.stress.binding.replace('_', ' ')],
    ['Take-out max', usd(result.exit.takeout_max), usd(result.stress.takeout_max)],
    ['Payoff', usd(result.exit.payoff), usd(result.stress.payoff)],
    ['Refi cushion', usd(result.exit.refi_cushion), usd(result.stress.refi_cushion)],
    ['Exit DSCR', mult(result.exit.exit_dscr), mult(result.stress.exit_dscr)],
  ]
  return (
    <table className="w-full text-sm">
      <thead className="text-xs text-slate-400">
        <tr>
          <th className="text-left font-medium" />
          <th className="text-right font-medium">Base</th>
          <th className="text-right font-medium">Stress</th>
        </tr>
      </thead>
      <tbody>
        {rows.map(([label, a, b]) => (
          <tr key={label} className="border-t border-slate-100">
            <td className="py-1.5">{label}</td>
            <td className="py-1.5 text-right font-mono">{a}</td>
            <td className="py-1.5 text-right font-mono">{b}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function CheckBlock({ check }: { check: CheckReport }) {
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <Chip tone={tone(check.status)}>{check.status}</Chip>
        <span className="text-sm text-slate-600">{check.summary}</span>
      </div>
      <ul className="space-y-1 text-sm">
        {check.checks.map((c) => (
          <li key={c.name} className="flex items-center gap-2">
            <span className={c.status === 'pass' ? 'text-teal-600' : c.status === 'warn' ? 'text-amber-600' : 'text-coral-600'}>
              {c.status === 'pass' ? '✓' : c.status === 'warn' ? '!' : '✕'}
            </span>
            <span className="font-mono text-xs">{c.name}</span>
          </li>
        ))}
      </ul>
      {check.mismatches.length > 0 && (
        <div className="space-y-2">
          {check.mismatches.map((m) => (
            <div key={m.field} className="rounded-md border border-coral-200 bg-coral-50 p-3 text-xs">
              <div className="font-medium text-coral-700">{m.field}</div>
              <div>
                underwriter {val(m.underwriter)} · independent {val(m.independent)} · diff {val(m.diff)}
              </div>
              {m.likely_cause && <div className="mt-1 text-slate-600">{m.likely_cause}</div>}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default function Calculations({
  deal, result, check, events, onViewSource,
}: {
  deal: Deal; result: UnderwritingResult; check: CheckReport | null; events: ApiEvent[]
  onViewSource: (doc: string, locator: string) => void
}) {
  return (
    <div className="space-y-4 p-4">
      <Section title="Recommendation (the AI call is a recommendation; you decide)">
        <div className="flex items-center gap-3">
          <CallChip call={result.call} />
          <span className="text-xs text-slate-400">
            rules {result.rules_version} · deal v{result.deal_version}
          </span>
        </div>
        {result.reasons.length === 0 ? (
          <p className="mt-2 text-sm text-slate-600">No rule was triggered.</p>
        ) : (
          <ul className="mt-3 space-y-2">
            {result.reasons.map((r) => (
              <li key={r.code} className="flex flex-wrap items-center gap-2 text-sm">
                <Chip tone={r.severity === 'decline' ? 'coral' : 'amber'}>{r.severity}</Chip>
                <span className="font-mono text-xs font-medium">{r.code}</span>
                <span className="text-slate-500">
                  value {reasonValue(r.code, r.value)} vs threshold {reasonValue(r.code, r.threshold)}
                </span>
              </li>
            ))}
          </ul>
        )}
        {result.overrides.length > 0 && (
          <div className="mt-3 rounded-md bg-sky-50 p-3 text-xs text-sky-800">
            <div className="font-medium">Reviewer overrides (numbers unchanged)</div>
            {result.overrides.map((o) => (
              <div key={o}>{o}</div>
            ))}
          </div>
        )}
      </Section>

      <Section title="Metrics (click one for its formula, inputs and sources)">
        {Object.entries(result.metrics).map(([k, v]) => (
          <MetricRow key={k} k={k} value={v} result={result} deal={deal} events={events}
            onViewSource={onViewSource} />
        ))}
      </Section>

      <Section title="Exit and stress">
        <ExitTable result={result} />
      </Section>

      <Section title="Reconciliation">
        <ul className="space-y-1.5 text-sm">
          {result.reconciliation.map((r) => (
            <li key={r.name} className="flex items-center gap-2">
              <Chip tone={tone(r.status)}>{r.status}</Chip>
              <span className="font-mono text-xs">{r.name}</span>
              {r.gap != null && <span className="text-slate-500">gap {pct(r.gap)}</span>}
              {r.detail && <span className="text-slate-500">{r.detail}</span>}
            </li>
          ))}
        </ul>
      </Section>

      {check && (
        <Section title="Independent check">
          <CheckBlock check={check} />
        </Section>
      )}

      {(result.flags.length > 0 || result.open_questions.length > 0) && (
        <Section title="Exceptions and questions for the sponsor">
          <ul className="space-y-1.5 text-sm">
            {result.flags.map((f) => (
              <li key={f.code}>
                <span className="font-mono text-xs font-medium">{f.code}</span>{' '}
                <span className="text-slate-600">{f.message}</span>
              </li>
            ))}
            {result.open_questions.map((q) => (
              <li key={q} className="text-slate-600">? {q}</li>
            ))}
          </ul>
        </Section>
      )}
    </div>
  )
}
