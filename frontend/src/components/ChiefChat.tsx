import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import type { Patch } from '../api/client'
import { pct, usd } from '../lib/format'
import { REVIEWER_PROMPTS } from '../lib/samples'
import { Button } from './Chips'

interface Msg {
  from: 'you' | 'chief'
  text: string
  patch?: Patch
}

function showValue(path: string, v: unknown): string {
  if (typeof v === 'number') return path.includes('note_rate') ? pct(v) : usd(v)
  return v == null ? '–' : String(v)
}

function PatchCard({
  patch, status, busy, onConfirm, onCancel,
}: {
  patch: Patch
  status: 'proposed' | 'confirmed' | 'cancelled'
  busy: boolean
  onConfirm: () => void
  onCancel: () => void
}) {
  const kind = { data: 'Data edit', narrative: 'Narrative edit', override: 'Judgment override' }[patch.kind]
  return (
    <div className="mt-2 rounded-lg border border-slate-300 bg-white p-3 text-xs shadow-sm">
      <div className="flex items-center justify-between">
        <span className="font-semibold text-slate-800">{kind}</span>
        <span className="font-mono text-slate-400">{patch.patch_id}</span>
      </div>
      <div className="mt-2 font-mono text-slate-700">{patch.path}</div>
      {patch.kind === 'data' && (
        <div className="mt-1 text-sm">
          <span className="text-slate-500 line-through">{showValue(patch.path, patch.old)}</span>
          {' → '}
          <span className="font-semibold text-teal-700">{showValue(patch.path, patch.new)}</span>
        </div>
      )}
      {patch.kind === 'narrative' && (
        <div className="mt-1 whitespace-pre-wrap rounded bg-slate-50 p-2 text-slate-700">{String(patch.new)}</div>
      )}
      {patch.kind === 'override' && (
        <div className="mt-1 text-slate-700">{String(patch.new)} (numbers unchanged)</div>
      )}
      {patch.reason && <div className="mt-1 text-slate-500">Reason: {patch.reason}</div>}
      {status === 'proposed' ? (
        <div className="mt-3 flex gap-2">
          <Button tone="primary" onClick={onConfirm} disabled={busy}>
            {busy ? 'Applying…' : 'Confirm'}
          </Button>
          <Button onClick={onCancel} disabled={busy}>
            Cancel
          </Button>
        </div>
      ) : (
        <div className={`mt-2 font-medium ${status === 'confirmed' ? 'text-teal-700' : 'text-slate-400'}`}>
          {status === 'confirmed' ? 'Confirmed' : 'Cancelled'}
        </div>
      )}
    </div>
  )
}

export default function ChiefChat({
  dealId, enabled, pending,
}: { dealId: string; enabled: boolean; pending: Patch[] }) {
  const [msgs, setMsgs] = useState<Msg[]>([
    {
      from: 'chief',
      text:
        'Ask me about this deal, or tell me what to change. Questions are answered from the tool ' +
        'record. Nothing is edited until you press Confirm.',
    },
  ])
  const [resolved, setResolved] = useState<Record<string, 'confirmed' | 'cancelled'>>({})
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [applying, setApplying] = useState<string | null>(null)
  const bottom = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: 'smooth' })
  }, [msgs])

  const say = (m: Msg) => setMsgs((prev) => [...prev, m])
  const statusOf = (p: Patch) => resolved[p.patch_id] ?? 'proposed'
  // A patch proposed earlier (or in another tab) that is still waiting for a click.
  const shown = new Set(msgs.flatMap((x) => (x.patch ? [x.patch.patch_id] : [])))
  const waiting = pending.filter((p) => !shown.has(p.patch_id) && !resolved[p.patch_id])

  const send = async (message: string) => {
    const m = message.trim()
    if (!m || busy) return
    setText('')
    say({ from: 'you', text: m })
    setBusy(true)
    try {
      const r = await api.chiefChat(dealId, m)
      say({ from: 'chief', text: r.reply, patch: r.patch ?? undefined })
    } catch (e) {
      say({ from: 'chief', text: (e as Error).message })
    } finally {
      setBusy(false)
    }
  }

  const confirm = async (p: Patch) => {
    setApplying(p.patch_id)
    try {
      await api.confirmPatch(dealId, p.patch_id)
      setResolved((r) => ({ ...r, [p.patch_id]: 'confirmed' }))
      say({
        from: 'chief',
        text:
          p.kind === 'data'
            ? 'Applied. A new deal version was created and underwriting and the independent check re-ran.'
            : 'Applied. The memo was re-rendered and its numbers re-checked.',
      })
    } catch (e) {
      say({ from: 'chief', text: `I couldn't apply that: ${(e as Error).message}` })
    } finally {
      setApplying(null)
    }
  }

  const cancel = async (p: Patch) => {
    try {
      await api.cancelPatch(dealId, p.patch_id)
      setResolved((r) => ({ ...r, [p.patch_id]: 'cancelled' }))
    } catch (e) {
      say({ from: 'chief', text: (e as Error).message })
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-slate-200 px-4 py-3">
        <h2 className="eyebrow !text-ink">Chief chat</h2>
        <p className="text-xs text-slate-500">Reviewer only. The chief reads your message; code answers.</p>
      </div>
      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
        {msgs.map((m, i) => (
          <div key={i} className={m.from === 'you' ? 'flex justify-end' : ''}>
            <div className={`max-w-[92%] ${m.from === 'you' ? '' : 'w-full'}`}>
              <div
                className={`whitespace-pre-wrap px-3.5 py-2 text-sm leading-relaxed ${
                  m.from === 'you' ? 'bg-ink text-paper' : 'border-l-2 border-ink bg-paper text-slate-800'
                }`}
              >
                {m.text}
              </div>
              {m.patch && (
                <PatchCard
                  patch={m.patch}
                  status={statusOf(m.patch)}
                  busy={applying === m.patch.patch_id}
                  onConfirm={() => void confirm(m.patch!)}
                  onCancel={() => void cancel(m.patch!)}
                />
              )}
            </div>
          </div>
        ))}
        {waiting.map((p) => (
          <div key={p.patch_id}>
            <div className="border-l-2 border-ink bg-paper px-3.5 py-2 text-sm text-slate-800">
              A change is waiting for your decision:
            </div>
            <PatchCard patch={p} status="proposed" busy={applying === p.patch_id}
              onConfirm={() => void confirm(p)} onCancel={() => void cancel(p)} />
          </div>
        ))}
        {busy && <div className="text-xs text-slate-400">…</div>}
        <div ref={bottom} />
      </div>
      <div className="border-t border-slate-200 p-3">
        {enabled ? (
          <>
            <div className="mb-2 flex max-h-24 flex-wrap gap-1.5 overflow-y-auto">
              {REVIEWER_PROMPTS.map((p) => (
                <button
                  key={p}
                  onClick={() => setText(p)}
                  className="rounded-[2px] border border-slate-300 bg-white px-2.5 py-1 text-left text-[11px] text-slate-500 hover:border-ink hover:text-ink"
                >
                  {p.length > 44 ? `${p.slice(0, 42)}…` : p}
                </button>
              ))}
            </div>
            <form
              onSubmit={(e) => {
                e.preventDefault()
                void send(text)
              }}
              className="flex gap-2"
            >
              <input
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="Ask or request a change"
                className="min-w-0 flex-1 rounded-[2px] border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-ink"
              />
              <Button type="submit" tone="primary" disabled={busy || !text.trim()}>
                Send
              </Button>
            </form>
          </>
        ) : (
          <p className="text-xs text-slate-500">The chat opens once underwriting has produced a result.</p>
        )}
      </div>
    </div>
  )
}
