import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../../api/client'
import type { Checklist } from '../../api/client'
import { useDebounced, useStream } from '../../api/hooks'
import ChecklistChips from './ChecklistChips'
import { Page } from '../../ui/Shell'
import { SAMPLE_FACTS } from '../../lib/samples'

interface Msg {
  from: 'agent' | 'you' | 'file'
  text: string
}

const GREETING: Msg = {
  from: 'agent',
  text:
    'Hi, I can help you submit a bridge loan package. Drop your documents here (deal summary, ' +
    'purchase contract, rent roll, T-12 and renovation budget) and tell me the deal basics. ' +
    'This is a sample-data prototype, so please use sample data only.',
}

export default function Chat({ dealId: initialId }: { dealId: string | null }) {
  // The deal is created on the first message or upload, not when the page opens, so browsing to
  // "New deal" and leaving never litters the queue with empty deals.
  const [dealId, setDealId] = useState<string | null>(initialId)
  const creating = useRef<Promise<string> | null>(null)
  const [msgs, setMsgs] = useState<Msg[]>([GREETING])
  const [checklist, setChecklist] = useState<Checklist | null>(null)
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [drag, setDrag] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const posted = useRef(new Set<string>())
  const bottom = useRef<HTMLDivElement>(null)
  const picker = useRef<HTMLInputElement>(null)

  const ensureDeal = useCallback((): Promise<string> => {
    if (initialId) return Promise.resolve(initialId)
    creating.current ??= api.createDeal().then((d) => {
      setDealId(d.deal_id)
      setChecklist(d.checklist)
      // Put the id in the address bar without remounting this page.
      window.history.replaceState(null, '', `#/chat/${d.deal_id}`)
      return d.deal_id
    })
    return creating.current
  }, [initialId])

  useEffect(() => {
    if (!initialId) return
    api.intakeStatus(initialId).then((s) => {
      setChecklist(s.checklist)
      if (s.stage !== 'Awaiting docs') {
        setSubmitted(true)
        setMsgs((m) => [...m, { from: 'agent', text: s.message }])
        posted.current.add(s.message)
      }
    }, () => undefined)
  }, [initialId])

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: 'smooth' })
  }, [msgs])

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
    if (!message || busy) return
    setText('')
    say({ from: 'you', text: message })
    setBusy(true)
    try {
      afterReply(await api.chat(await ensureDeal(), message))
    } catch (e) {
      say({ from: 'agent', text: `Sorry, something went wrong: ${(e as Error).message}` })
    } finally {
      setBusy(false)
    }
  }

  const upload = async (files: FileList | File[]) => {
    setBusy(true)
    for (const file of Array.from(files)) {
      say({ from: 'file', text: file.name })
      try {
        afterReply(await api.upload(await ensureDeal(), file))
      } catch (e) {
        say({ from: 'agent', text: `I couldn't take ${file.name}: ${(e as Error).message}` })
      }
    }
    setBusy(false)
  }

  return (
    <Page external>
    <div className="mx-auto flex h-full max-w-2xl flex-col px-6 pb-6 pt-8">
      <header>
        <div className="eyebrow">Intake</div>
        <h1 className="mt-1 text-[30px] leading-tight">Submit a bridge loan package</h1>
        <p className="mt-1 text-sm text-slate-500">
          Sample data only{dealId ? ` · reference ${dealId}` : ' · a reference is assigned when you send your first message'}
        </p>
      </header>

      <div className="mt-5 border border-slate-200 bg-white p-3.5">
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
        className={`mt-4 min-h-0 flex-1 space-y-3 overflow-y-auto border bg-white p-4 ${
          drag ? 'border-ink outline outline-2 outline-ink' : 'border-slate-200'
        }`}
      >
        {msgs.map((m, i) =>
          m.from === 'file' ? (
            <div key={i} className="flex justify-end">
              <span className="border border-slate-300 px-3 py-1.5 font-mono text-xs text-slate-600">
                {m.text} uploaded
              </span>
            </div>
          ) : (
            <div key={i} className={`flex ${m.from === 'you' ? 'justify-end' : ''}`}>
              <div
                className={`max-w-[85%] whitespace-pre-wrap px-4 py-2.5 text-sm leading-relaxed ${
                  m.from === 'you' ? 'bg-ink text-paper' : 'border-l-2 border-ink bg-paper text-slate-800'
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
            className="rounded-[2px] border border-slate-300 bg-white px-2.5 py-1 text-xs text-slate-500 hover:border-ink hover:text-ink"
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
          className="rounded-[2px] border border-ink px-4 text-sm font-semibold hover:bg-ink hover:text-paper"
          title="Attach files (or drop them on the chat)"
        >
          Attach
        </button>
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Type a message or drop files"
          className="flex-1 rounded-[2px] border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-ink"
        />
        <button
          type="submit"
          disabled={busy || !text.trim()}
          className="rounded-[2px] border border-ink bg-ink px-5 text-sm font-semibold text-paper hover:bg-slate-700 disabled:border-slate-300 disabled:bg-transparent disabled:text-slate-400"
        >
          Send
        </button>
      </form>
    </div>
    </Page>
  )
}
