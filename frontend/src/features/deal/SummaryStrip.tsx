import type { DealDetail } from '../../api/client'
import { CallChip, Chip } from '../../ui/Chip'

const CHECK_TEXT: Record<string, { tone: 'teal' | 'amber' | 'coral'; text: string }> = {
  pass: { tone: 'teal', text: 'Checker agrees' },
  warn: { tone: 'amber', text: 'Checker: warnings' },
  fail: { tone: 'coral', text: 'Checker disagrees' },
}

/** The deal's standing in one line: call, check, flags, questions. It replaces the status that
 *  used to be repeated in the header, the timeline and the flow graph. */
export default function SummaryStrip({ detail }: { detail: DealDetail }) {
  const { status, result, check } = detail
  if (!result)
    return (
      <p className="border-b border-slate-200 bg-white px-6 py-2 text-sm text-slate-600">
        {status.next_action}
      </p>
    )
  const modelRead = result.flags.some((f) => f.code === 'MODEL_ASSISTED_EXTRACTION')
  const questions = result.open_questions.length
  const c = check ? CHECK_TEXT[check.status] : null
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-slate-200 bg-white px-6 py-2"
      aria-label="Summary">
      <span className="flex items-center gap-2 text-sm text-slate-600">
        Call <CallChip call={result.call} />
      </span>
      {c && <Chip tone={c.tone}>{c.text}</Chip>}
      {status.escalation && <Chip tone="coral">Escalated after retries</Chip>}
      <span className="text-sm text-slate-600">
        {result.flags.length} {result.flags.length === 1 ? 'flag' : 'flags'}
      </span>
      <span className="text-sm text-slate-600">
        {questions} open {questions === 1 ? 'question' : 'questions'}
      </span>
      {modelRead && (
        <Chip tone="sky" title="Fields a model read from the documents, each checked against a quote">
          Model-read fields: please confirm
        </Chip>
      )}
      <span className="ml-auto text-xs text-slate-500">
        rules {result.rules_version} · version {status.deal_version}
      </span>
    </div>
  )
}
