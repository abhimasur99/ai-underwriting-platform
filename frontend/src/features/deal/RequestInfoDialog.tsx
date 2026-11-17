import { useState } from 'react'
import { api } from '../../api/client'
import { Button } from '../../ui/Button'
import { Dialog } from '../../ui/Dialog'

/** Ask the sponsor for something. The note appears in their intake chat; the deal waits. */
export default function RequestInfoDialog({
  dealId, initial, onClose,
}: { dealId: string; initial: string | null; onClose: () => void }) {
  const open = initial !== null
  return (
    <Dialog open={open} onClose={onClose} title="Ask the sponsor for more information">
      {open && <Form key={initial} dealId={dealId} initial={initial ?? ''} onClose={onClose} />}
    </Dialog>
  )
}

function Form({ dealId, initial, onClose }: { dealId: string; initial: string; onClose: () => void }) {
  const [note, setNote] = useState(initial)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const send = async () => {
    setBusy(true)
    setError(null)
    try {
      await api.decide(dealId, 'request_info', note.trim())
      onClose()
    } catch (e) {
      setError((e as Error).message)
      setBusy(false)
    }
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        void send()
      }}
    >
      <p className="mt-2 text-sm text-slate-600">
        Your note appears in the sponsor’s intake chat, and the deal waits for their answer. A
        reply in words returns it to you as it is; a new file is read again as a new version.
      </p>
      <label htmlFor="info-note" className="eyebrow mt-4 block !text-ink">What do you need?</label>
      <textarea
        id="info-note"
        autoFocus
        rows={4}
        value={note}
        onChange={(e) => setNote(e.target.value)}
        className="mt-1 w-full border border-slate-300 bg-white p-2 text-sm outline-none focus:border-ink"
      />
      {error && <p role="alert" className="mt-2 text-xs text-coral-700">{error}</p>}
      <div className="mt-4 flex justify-end gap-2">
        <Button onClick={onClose}>Cancel</Button>
        <Button type="submit" tone="primary" disabled={busy || !note.trim()}>
          {busy ? 'Sending…' : 'Send to sponsor'}
        </Button>
      </div>
    </form>
  )
}
