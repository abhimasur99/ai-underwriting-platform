import { useState } from 'react'
import { api } from '../api/client'
import { Button, Chip } from './Chips'

const FINAL: Record<string, { tone: 'teal' | 'coral'; text: string }> = {
  APPROVED: { tone: 'teal', text: 'Approved' },
  RELEASED: { tone: 'teal', text: 'Approved and released' },
  REJECTED: { tone: 'coral', text: 'Rejected' },
}

/** The human decision. The AI call is a recommendation; only these buttons record a decision. */
export default function DecisionBar({
  dealId, state, escalated,
}: { dealId: string; state: string; escalated: boolean }) {
  const [rationale, setRationale] = useState('')
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const final = FINAL[state]
  const open = state === 'NEEDS_REVIEW'

  const decide = async (decision: 'approve' | 'send_back' | 'reject') => {
    if (decision === 'approve' && escalated &&
      !window.confirm('The independent check kept failing and this deal was escalated. Approve anyway?'))
      return
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

  return (
    <div className="flex flex-wrap items-center gap-3 border-b border-slate-200 bg-white px-4 py-2.5">
      {final ? (
        <Chip tone={final.tone}>{final.text}</Chip>
      ) : (
        <span className="text-xs text-slate-500">
          {open ? 'Your decision' : 'Decision opens when the deal reaches review'}
        </span>
      )}
      <input
        value={rationale}
        onChange={(e) => setRationale(e.target.value)}
        disabled={!open}
        placeholder="Rationale (optional)"
        className="min-w-48 flex-1 rounded-md border border-slate-300 px-3 py-1.5 text-sm outline-none focus:border-teal-600 disabled:bg-slate-50"
      />
      <Button tone="primary" disabled={!open || busy !== null} onClick={() => void decide('approve')}>
        {busy === 'approve' ? 'Approving…' : 'Approve'}
      </Button>
      <Button disabled={!open || busy !== null} onClick={() => void decide('send_back')}
        title="Re-run underwriting and the check on the current version">
        {busy === 'send_back' ? 'Sending back…' : 'Send back'}
      </Button>
      <Button tone="danger" disabled={!open || busy !== null} onClick={() => void decide('reject')}>
        Reject
      </Button>
      {error && <span className="w-full text-xs text-coral-700">{error}</span>}
    </div>
  )
}
