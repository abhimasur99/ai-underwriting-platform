import { useState } from 'react'
import { api } from '../api/client'
import { Button, Chip } from './Chips'

type Decision = 'approve' | 'send_back' | 'reject'

const FINAL: Record<string, { tone: 'teal' | 'coral'; text: string }> = {
  APPROVED: { tone: 'teal', text: 'Approved' },
  RELEASED: { tone: 'teal', text: 'Approved and released' },
  REJECTED: { tone: 'coral', text: 'Rejected' },
}

// What each button really does in this prototype (see Chief.decide in the backend).
const EXPLAIN: Record<Decision, { label: string; what: string; confirm: string }> = {
  approve: {
    label: 'Approve',
    what: 'Records your approval and closes the deal. A released snapshot (deal data, result, check and your rationale) is saved next to the memo. Nothing is sent outside this app.',
    confirm: 'Approve this deal and close it?',
  },
  send_back: {
    label: 'Send back',
    what: 'Runs underwriting and the independent check again on the current deal version, then returns the deal here. Use it to retry after a flag or a failed check. It does not message anyone.',
    confirm: 'Re-run underwriting and the check?',
  },
  reject: {
    label: 'Reject',
    what: 'Closes the deal as rejected and logs your rationale. This is final: a closed deal cannot be reopened.',
    confirm: 'Reject this deal and close it?',
  },
}

/** The human decision. The AI call is a recommendation; only these buttons record a decision. */
export default function DecisionBar({
  dealId, state, escalated,
}: { dealId: string; state: string; escalated: boolean }) {
  const [rationale, setRationale] = useState('')
  const [asking, setAsking] = useState<Decision | null>(null)
  const [busy, setBusy] = useState<Decision | null>(null)
  const [help, setHelp] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const final = FINAL[state]
  const open = state === 'NEEDS_REVIEW'

  const run = async (decision: Decision) => {
    setAsking(null)
    setBusy(decision)
    setError(null)
    try {
      await api.decide(dealId, decision, rationale.trim())
      setRationale('')
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(null)
    }
  }

  const ask = (d: Decision) => {
    setError(null)
    setAsking(d)
  }

  return (
    <div className="border-b border-slate-200 bg-white px-5 py-3">
      <div className="flex flex-wrap items-center gap-3">
        <div className="eyebrow w-28 shrink-0">{final ? 'Decision' : 'Your decision'}</div>
        {final ? (
          <Chip tone={final.tone}>{final.text}</Chip>
        ) : (
          <>
            <input
              value={rationale}
              onChange={(e) => setRationale(e.target.value)}
              disabled={!open}
              aria-label="Rationale"
              placeholder={open ? 'Rationale (optional)' : 'Opens when the deal reaches review'}
              className="min-w-48 flex-1 border-b border-slate-300 bg-transparent px-1 py-1.5 text-sm outline-none focus:border-ink disabled:text-slate-400"
            />
            <Button tone="primary" disabled={!open || busy !== null} onClick={() => ask('approve')}>
              {busy === 'approve' ? 'Approving…' : 'Approve'}
            </Button>
            <Button disabled={!open || busy !== null} onClick={() => ask('send_back')}>
              {busy === 'send_back' ? 'Sending back…' : 'Send back'}
            </Button>
            <Button tone="danger" disabled={!open || busy !== null} onClick={() => ask('reject')}>
              {busy === 'reject' ? 'Rejecting…' : 'Reject'}
            </Button>
          </>
        )}
        <button
          onClick={() => setHelp(!help)}
          aria-expanded={help}
          className="text-xs font-semibold text-slate-500 underline underline-offset-4 hover:text-ink"
        >
          {help ? 'Hide' : 'What do these do?'}
        </button>
      </div>

      {asking && (
        <div className="mt-3 flex flex-wrap items-center gap-3 border border-ink bg-paper px-4 py-2.5 text-sm">
          <span className="font-semibold">{EXPLAIN[asking].confirm}</span>
          {asking === 'approve' && escalated && (
            <span className="text-coral-700">
              The independent check kept failing and this deal was escalated.
            </span>
          )}
          <span className="ml-auto flex gap-2">
            <Button tone={asking === 'reject' ? 'danger' : 'primary'} onClick={() => void run(asking)}>
              Yes, {EXPLAIN[asking].label.toLowerCase()}
            </Button>
            <Button onClick={() => setAsking(null)}>Cancel</Button>
          </span>
        </div>
      )}

      {help && (
        <dl className="mt-3 grid gap-x-8 gap-y-3 border-t border-slate-200 pt-3 text-xs text-slate-600 md:grid-cols-3">
          {(Object.keys(EXPLAIN) as Decision[]).map((d) => (
            <div key={d}>
              <dt className="eyebrow !text-ink">{EXPLAIN[d].label}</dt>
              <dd className="mt-1 leading-relaxed">{EXPLAIN[d].what}</dd>
            </div>
          ))}
        </dl>
      )}
      {error && <p className="mt-2 text-xs text-coral-700">{error}</p>}
    </div>
  )
}
