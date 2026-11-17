import { useState } from 'react'
import { api } from '../../api/client'
import { Button } from '../../ui/Button'
import { Chip } from '../../ui/Chip'

type Decision = 'approve' | 'reject'

const FINAL: Record<string, { tone: 'teal' | 'coral'; text: string }> = {
  APPROVED: { tone: 'teal', text: 'Approved' },
  RELEASED: { tone: 'teal', text: 'Approved' },
  REJECTED: { tone: 'coral', text: 'Rejected' },
}

// What each action really does in this prototype (see Chief.decide in the backend).
const EXPLAIN = [
  ['Reject', 'Closes the deal as rejected and logs your rationale. This is final: a closed deal cannot be reopened.'],
  ['Request info', 'Asks the sponsor for something. Your note appears in their intake chat and the deal waits. A reply in words returns it to you as it is; a new file is read again as a new version.'],
  ['Approve', 'Records your approval and closes the deal. A released snapshot (deal data, result, check and your rationale) is saved beside the memo. A draft reply to the broker opens for you to edit; nothing is sent outside this app.'],
] as const

const CONFIRM: Record<Decision, string> = {
  approve: 'Approve this deal and close it?',
  reject: 'Reject this deal and close it?',
}

/** Reject on the left, the primary action on the right. The AI call is a recommendation; only
 *  these buttons record a decision. */
export default function DecisionActions({
  dealId, state, escalated, onRequestInfo, onReply,
}: {
  dealId: string; state: string; escalated: boolean; onRequestInfo: () => void; onReply: () => void
}) {
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
      await api.decide(dealId, decision, '')
      onReply()          // the reply to the broker is drafted with the decision
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(null)
    }
  }

  if (final)
    return (
      <div className="flex items-center gap-2">
        <Chip tone={final.tone}>{final.text}</Chip>
        <Button onClick={onReply} title="The draft reply to the broker. It is never sent from this app.">
          Reply to broker
        </Button>
      </div>
    )

  return (
    <div className="relative">
      <div className="flex items-center gap-2">
        <button
          onClick={() => setHelp(!help)}
          aria-expanded={help}
          aria-label="What do these actions do?"
          title="What do these actions do?"
          className="mr-1 h-7 w-7 border border-slate-300 text-xs font-bold text-slate-500 hover:border-ink hover:text-ink"
        >
          ?
        </button>
        <Button tone="danger" disabled={!open || busy !== null} onClick={() => setAsking('reject')}>
          {busy === 'reject' ? 'Rejecting…' : 'Reject'}
        </Button>
        <Button disabled={!open || busy !== null} onClick={onRequestInfo}>
          Request info
        </Button>
        <Button tone="primary" disabled={!open || busy !== null} onClick={() => setAsking('approve')}>
          {busy === 'approve' ? 'Approving…' : 'Approve'}
        </Button>
      </div>

      {(asking || help || error) && (
        <div className="absolute right-0 top-full z-20 mt-2 w-[26rem] max-w-[90vw] border border-ink bg-white p-4 shadow-xl">
          {asking && (
            <div role="group" aria-label="Confirm">
              <p className="text-sm font-semibold">{CONFIRM[asking]}</p>
              {asking === 'approve' && escalated && (
                <p className="mt-1 text-xs text-coral-700">
                  The independent check kept failing and this deal was escalated.
                </p>
              )}
              <div className="mt-3 flex justify-end gap-2">
                <Button onClick={() => setAsking(null)}>Cancel</Button>
                <Button tone={asking === 'reject' ? 'danger' : 'primary'} onClick={() => void run(asking)}>
                  Yes, {asking}
                </Button>
              </div>
            </div>
          )}
          {help && !asking && (
            <dl className="space-y-3 text-xs text-slate-600">
              {EXPLAIN.map(([name, text]) => (
                <div key={name}>
                  <dt className="eyebrow !text-ink">{name}</dt>
                  <dd className="mt-0.5 leading-relaxed">{text}</dd>
                </div>
              ))}
            </dl>
          )}
          {error && <p role="alert" className="text-xs text-coral-700">{error}</p>}
        </div>
      )}
    </div>
  )
}
