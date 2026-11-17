import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import type { Checklist } from '../api/client'
import { useDebounced, useStream } from '../api/hooks'
import ChecklistChips from '../components/ChecklistChips'
import { navigate } from '../lib/router'
import { SAMPLE_FACTS } from '../lib/samples'

interface Msg {
  from: 'agent' | 'you' | 'file'
  text: string
}

// StrictMode runs effects twice in development; this keeps that from creating two deals.
let creating: Promise<string> | null = null
function createOnce(): Promise<string> {
  creating ??= api.createDeal().then((d) => d.deal_id)
  return creating
}

const GREETING: Msg = {
  from: 'agent',
  text:
    'Hi, I can help you submit a bridge loan package. Drop your documents here (deal summary, ' +
    'purchase contract, rent roll, T-12 and renovation budget) and tell me the deal basics. ' +
    'This is a sample-data prototype, so please use sample data only.',
}

export default function Chat({ dealId }: { dealId: string | null }) {
  const [msgs, setMsgs] = useState<Msg[]>([GREETING])
  const [checklist, setChecklist] = useState<Checklist | null>(null)
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [drag, setDrag] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const posted = useRef(new Set<string>())
  const bottom = useRef<HTMLDivElement>(null)
  const picker = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (dealId) return
    createOnce().then((id) => navigate(`chat/${id}`, true))
  }, [dealId])

  useEffect(() => {
    if (!dealId) return
    api.intakeStatus(dealId).then((s) => {
      setChecklist(s.checklist)
      if (s.stage !== 'Awaiting docs') {
        setSubmitted(true)
        setMsgs((m) => [...m, { from: 'agent', text: s.message }])
        posted.current.add(s.message)
      }
    }, () => undefined)
  }, [dealId])

  useEffect(() => bottom.current?.scrollIntoView({ behavior: 'smooth' }), [msgs])

  // Status posted into the chat from deal state. Only plain sentences, never numbers or a call.
  const postStatus = useCallback(() => {
    if (!dealId || !submitted) return
    api.intakeStatus(dealId).then((s) => {
      setChecklist(s.checklist)
      if (posted.current.has(s.message)) return
      posted.current.add(s.message)
      setMsgs((m) => [...m, { from: 'agent', text: s.message }])
    }, () => undefined)
  }, [dealId, submitted])
  const refresh = useDebounced(postStatus, 150)
  useStream(dealId && submitted ? `/api/deals/${dealId}/stream` : null, refresh)

  const say = (m: Msg) => setMsgs((prev) => [...prev, m])

  const afterReply = (r: { reply: string; checklist: Checklist; submitted?: boolean }) => {
    setChecklist(r.checklist)
    say({ from: 'agent', text: r.reply })
    if (r.submitted) setSubmitted(true)
  }

  const send = async () => {
    const message = text.trim()
    if (!message || !dealId || busy) return
    setText('')
    say({ from: 'you', text: message })
    setBusy(true)
    try {
      afterReply(await api.chat(dealId, message))
    } catch (e) {
      say({ from: 'agent', text: `Sorry, something went wrong: ${(e as Error).message}` })
    } finally {
      setBusy(false)
    }
  }

  const upload = async (files: FileList | File[]) => {
    if (!dealId) return
    setBusy(true)
    for (const file of Array.from(files)) {
      say({ from: 'file', text: file.name })
      try {
        afterReply(await api.upload(dealId, file))
      } catch (e) {
        say({ from: 'agent', text: `I couldn't take ${file.name}: ${(e as Error).message}` })
      }
    }
    setBusy(false)
  }

  return (
    <div className="mx-auto flex h-full max-w-2xl flex-col px-4 py-6">
      <header className="flex items-start justify-between">
        <div>
          <h1 className="text-lg font-semibold">Bridge loan intake</h1>
          <p className="text-xs text-slate-500">Sample data only · {dealId ?? 'starting…'}</p>
        </div>
        <a href="#/" className="text-xs text-slate-400 hover:text-slate-600">
          Internal queue →
        </a>
      </header>

      <div className="mt-4 rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
        <ChecklistChips checklist={checklist} />
      </div>

      <div
        onDragOver={(e) => {
          e.preventDefault()
          setDrag(true)
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDrag(false)
          if (e.dataTransfer.files.length) void upload(e.dataTransfer.files)
        }}
        className={`mt-4 flex-1 space-y-3 overflow-y-auto rounded-lg border bg-white p-4 shadow-sm ${
          drag ? 'border-teal-500 ring-2 ring-teal-500/30' : 'border-slate-200'
        }`}
      >
        {msgs.map((m, i) =>
          m.from === 'file' ? (
            <div key={i} className="flex justify-end">
              <span className="rounded-md bg-slate-100 px-3 py-1.5 font-mono text-xs text-slate-600">
                {m.text} uploaded
              </span>
            </div>
          ) : (
            <div key={i} className={`flex ${m.from === 'you' ? 'justify-end' : ''}`}>
              <div
                className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-4 py-2 text-sm ${
                  m.from === 'you' ? 'bg-teal-600 text-white' : 'bg-slate-100 text-slate-800'
                }`}
              >
                {m.text}
              </div>
            </div>
          ),
        )}
        {busy && <div className="text-xs text-slate-400">…</div>}
        <div ref={bottom} />
      </div>

      <div className="mt-3 flex flex-wrap gap-1.5">
        {SAMPLE_FACTS.map((s) => (
          <button
            key={s.label}
            onClick={() => setText(s.text)}
            title={`Fills the box with the facts for ${s.folder}`}
            className="rounded-full bg-white px-2.5 py-1 text-xs text-slate-500 ring-1 ring-inset ring-slate-300 hover:bg-slate-50"
          >
            {s.label}
          </button>
        ))}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault()
          void send()
        }}
        className="mt-2 flex gap-2"
      >
        <input ref={picker} type="file" multiple hidden onChange={(e) => e.target.files && void upload(e.target.files)} />
        <button
          type="button"
          onClick={() => picker.current?.click()}
          className="rounded-md bg-white px-3 text-sm text-slate-600 ring-1 ring-slate-300 hover:bg-slate-50"
          title="Attach files (or drop them on the chat)"
        >
          Attach
        </button>
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Type a message or drop files"
          className="flex-1 rounded-md border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-teal-600 focus:ring-1 focus:ring-teal-600"
        />
        <button
          type="submit"
          disabled={busy || !text.trim() || !dealId}
          className="rounded-md bg-teal-600 px-4 text-sm font-medium text-white hover:bg-teal-700 disabled:bg-teal-600/40"
        >
          Send
        </button>
      </form>
    </div>
  )
}
