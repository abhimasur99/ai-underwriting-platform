import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../../api/client'
import type { IntakeStatus } from '../../api/client'
import { useDebounced, useStream } from '../../api/hooks'
import { Page } from '../../ui/Shell'
import PackagePanel from './PackagePanel'

interface Msg {
  from: 'agent' | 'you' | 'file'
  text: string
}

const GREETING: Msg = {
  from: 'agent',
  text:
    'Hello, and welcome. I can help you submit your loan package. Please send your deal summary, ' +
    'purchase contract, rent roll, T-12 and renovation budget (PDF, Word, Excel or CSV). You can ' +
    'drop them in this chat or onto the checklist, and I will read the property details from ' +
    'them and tell you if anything is missing. This is a sample-data prototype, so please use ' +
    'sample data only.',
}

/** The sponsor's intake: the conversation on the left, what has arrived and what was read from it
 *  on the right. The deal is created on the first message or upload, not when the page opens. */
export default function Chat({ dealId: initialId }: { dealId: string | null }) {
  const [dealId, setDealId] = useState<string | null>(initialId)
  const creating = useRef<Promise<string> | null>(null)
  const [msgs, setMsgs] = useState<Msg[]>([GREETING])
  const [status, setStatus] = useState<IntakeStatus | null>(null)
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
      window.history.replaceState(null, '', `#/chat/${d.deal_id}`)
      return d.deal_id
    })
    return creating.current
  }, [initialId])

  // Reopening a conversation restores what was said, then the current status.
  useEffect(() => {
    if (!initialId) return
    Promise.all([api.transcript(initialId), api.intakeStatus(initialId)]).then(([log, s]) => {
      setStatus(s)
      setMsgs([GREETING, ...log.map((m) => ({ from: m.from as Msg['from'], text: m.text }))])
      if (s.stage !== 'Awaiting docs') {
        setSubmitted(true)
        posted.current.add(s.message)
        setMsgs((m) => (m.at(-1)?.text === s.message ? m : [...m, { from: 'agent', text: s.message }]))
      }
    }, () => undefined)
  }, [initialId])

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: 'smooth' })
  }, [msgs])

  const refreshStatus = useCallback((id: string) => {
    api.intakeStatus(id).then(setStatus, () => undefined)
  }, [])

  // Status posted into the chat from deal state: plain sentences, never numbers or a call.
  const postStatus = useCallback(() => {
    if (!dealId || !submitted) return
    api.intakeStatus(dealId).then((s) => {
      setStatus(s)
      if (posted.current.has(s.message)) return
      posted.current.add(s.message)
      setMsgs((m) => [...m, { from: 'agent', text: s.message }])
    }, () => undefined)
  }, [dealId, submitted])
  const refresh = useDebounced(postStatus, 150)
  useStream(dealId && submitted ? `/api/deals/${dealId}/stream` : null, refresh)

  const say = (m: Msg) => setMsgs((prev) => [...prev, m])

  const afterReply = (id: string, r: { reply: string; submitted?: boolean }) => {
    say({ from: 'agent', text: r.reply })
    if (r.submitted) setSubmitted(true)
    refreshStatus(id)
  }

  const send = async () => {
    const message = text.trim()
    if (!message || busy) return
    setText('')
    say({ from: 'you', text: message })
    setBusy(true)
    try {
      const id = await ensureDeal()
      afterReply(id, await api.chat(id, message))
    } catch (e) {
      say({ from: 'agent', text: `I'm sorry, something went wrong on our side: ${(e as Error).message}` })
    } finally {
      setBusy(false)
    }
  }

  const upload = async (files: FileList | File[], label?: string) => {
    setBusy(true)
    for (const file of Array.from(files)) {
      say({ from: 'file', text: file.name })
      try {
        const id = await ensureDeal()
        afterReply(id, await api.upload(id, file, label))
      } catch (e) {
        say({ from: 'agent', text: `I couldn't take ${file.name}: ${(e as Error).message}` })
      }
    }
    setBusy(false)
  }

  return (
    <Page external>
      <div className="mx-auto flex h-full max-w-6xl gap-8 px-6 pb-6 pt-8">
        <div className="flex min-w-0 flex-1 flex-col">
          <header>
            <div className="eyebrow">Intake</div>
            <h1 className="mt-1 text-[30px] leading-tight">Submit a bridge loan package</h1>
            <p className="mt-1 text-sm text-slate-600">
              Sample data only{dealId ? ` · reference ${dealId}` : ' · a reference is assigned when you send your first message'}
            </p>
          </header>

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
            role="log"
            aria-live="polite"
            aria-label="Conversation"
            className={`mt-5 min-h-0 flex-1 space-y-3 overflow-y-auto border bg-white p-4 ${
              drag ? 'border-ink outline outline-2 outline-ink' : 'border-slate-200'
            }`}
          >
            {msgs.map((m, i) =>
              m.from === 'file' ? (
                <div key={i} className="flex justify-end">
                  <span className="border border-slate-300 px-3 py-1.5 font-mono text-xs text-slate-600">
                    {m.text} sent
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
            {busy && <div className="text-xs text-slate-500">…</div>}
            <div ref={bottom} />
          </div>

          <form
            onSubmit={(e) => {
              e.preventDefault()
              void send()
            }}
            className="mt-3 flex gap-2"
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
              aria-label="Message"
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

        <PackagePanel status={status} busy={busy} onFile={(label, file) => void upload([file], label)} />
      </div>
    </Page>
  )
}
