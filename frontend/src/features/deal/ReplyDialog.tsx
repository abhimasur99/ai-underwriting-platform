import { useCallback, useEffect, useState } from 'react'
import { api } from '../../api/client'
import type { ReplyDraft } from '../../api/client'
import { Button } from '../../ui/Button'
import { Chip } from '../../ui/Chip'
import { Dialog } from '../../ui/Dialog'

const BLANK = /\[[^\]\n]+\]/g

/** The draft reply to the broker. Nothing is sent from this app: the reviewer edits the wording,
 *  approves it (a record in the log), and copies it into their own email. */
export default function ReplyDialog({
  dealId, open, onClose,
}: { dealId: string; open: boolean; onClose: () => void }) {
  return (
    <Dialog open={open} onClose={onClose} title="Reply to the broker" wide>
      {open && <Body dealId={dealId} onClose={onClose} />}
    </Dialog>
  )
}

function Body({ dealId, onClose }: { dealId: string; onClose: () => void }) {
  const [draft, setDraft] = useState<ReplyDraft | null | undefined>(undefined)
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const show = useCallback((d: ReplyDraft | null) => {
    setDraft(d)
    setText(d?.text ?? '')
  }, [])
  useEffect(() => {
    api.replyDraft(dealId).then(show, (e: Error) => {
      setDraft(null)
      setError(e.message)
    })
  }, [dealId, show])

  const run = async (label: string, work: () => Promise<ReplyDraft>) => {
    setBusy(true)
    setError(null)
    setNote(null)
    try {
      show(await work())
      setNote(label)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }
  const dirty = draft != null && text.trim() !== draft.text.trim()
  const blanks = [...new Set(text.match(BLANK) ?? [])]
  const approve = () => run('Wording approved. Nothing was sent.', async () => {
    if (dirty) await api.editReply(dealId, text)
    return api.approveReply(dealId)
  })
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text)
      setNote('Copied. Paste it into your email.')
    } catch {
      setNote('Your browser would not copy it; select the text and copy it yourself.')
    }
  }

  if (draft === undefined) return <p className="mt-3 text-sm text-slate-600">Loading…</p>
  if (draft === null)
    return (
      <div>
        <p className="mt-2 text-sm text-slate-600">
          There is no draft reply for this deal yet. I can write one from the decision.
        </p>
        {error && <p role="alert" className="mt-2 text-xs text-coral-700">{error}</p>}
        <div className="mt-4 flex justify-end gap-2">
          <Button onClick={onClose}>Close</Button>
          <Button tone="primary" disabled={busy} onClick={() => void run('Drafted.', () => api.draftReply(dealId))}>
            {busy ? 'Drafting…' : 'Draft a reply'}
          </Button>
        </div>
      </div>
    )

  return (
    <div>
      <p className="mt-2 text-sm text-slate-600">
        A {draft.decision === 'approve' ? 'next-steps' : 'decline'} reply, written from this deal. It
        quotes no ratio or figure from the calculations. Edit it, approve the wording, then copy it into
        your own email. <strong className="font-semibold text-ink">Nothing is sent from this app.</strong>
      </p>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Chip tone={draft.status === 'approved' && !dirty ? 'teal' : 'amber'}>
          {draft.status === 'approved' && !dirty ? 'Wording approved' : 'Draft'}
        </Chip>
        {draft.wording === 'claude' && <span className="text-xs text-slate-600">Wording smoothed by Claude</span>}
        {draft.edited && <span className="text-xs text-slate-600">Edited by you</span>}
      </div>
      <label htmlFor="reply-text" className="eyebrow mt-3 block !text-ink">Your reply</label>
      <textarea
        id="reply-text"
        rows={15}
        value={text}
        onChange={(e) => setText(e.target.value)}
        className="mt-1 w-full border border-slate-300 bg-white p-2 font-mono text-[13px] leading-relaxed outline-none focus:border-ink"
      />
      {blanks.length > 0 && (
        <p className="mt-1 text-xs text-amber-800">Fill in {blanks.join(', ')} before approving.</p>
      )}
      <p role="status" className="mt-1 min-h-4 text-xs text-slate-600">{note}</p>
      {error && <p role="alert" className="text-xs text-coral-700">{error}</p>}
      <div className="mt-3 flex flex-wrap justify-between gap-2">
        <Button disabled={busy} title="Discard your edits and write the draft again"
          onClick={() => void run('Started over from the decision.', () => api.draftReply(dealId))}>
          Start over
        </Button>
        <div className="flex gap-2">
          <Button onClick={() => void copy()}>Copy</Button>
          <Button disabled={busy || !dirty} onClick={() => void run('Saved.', () => api.editReply(dealId, text))}>
            Save changes
          </Button>
          <Button tone="primary" disabled={busy || blanks.length > 0 || !text.trim() || (draft.status === 'approved' && !dirty)}
            onClick={() => void approve()}>
            Approve wording
          </Button>
          <Button onClick={onClose}>Close</Button>
        </div>
      </div>
    </div>
  )
}
