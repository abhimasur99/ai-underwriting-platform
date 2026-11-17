import { useMemo, useState } from 'react'
import { useDealData, useQueue } from '../../api/hooks'
import { DEAL_TABS, resolveTab } from '../../lib/dealTabs'
import { deriveFlow } from '../../lib/flow'
import type { NodeId } from '../../lib/flow'
import { neighbours } from '../../lib/nav'
import { usePersisted } from '../../lib/persisted'
import { navigate } from '../../lib/router'
import { Page } from '../../ui/Shell'
import { TabPanel, Tabs } from '../../ui/Tabs'
import AttentionPanel from './AttentionPanel'
import ChatPane from './ChatPane'
import DealHeader from './DealHeader'
import FilesTab from './FilesTab'
import MemoViewer from './MemoViewer'
import NumbersTab from './NumbersTab'
import ProcessTab from './ProcessTab'
import RequestInfoDialog from './RequestInfoDialog'
import SummaryStrip from './SummaryStrip'

const ID = 'deal'

/** Chat on the left, the deal on the right. The header (and so the decision) stays on every tab. */
export default function DealPage({ dealId, tab }: { dealId: string; tab?: string }) {
  const { detail, events, error, reload } = useDealData(dealId)
  const { rows } = useQueue()
  const [selected, setSelected] = useState<NodeId | null>(null)
  const [focus, setFocus] = useState<{ doc: string; locator: string } | null>(null)
  const [infoDraft, setInfoDraft] = useState<string | null>(null)
  const [chatOpen, setChatOpen] = usePersisted('chatOpen', true)
  const [attentionOpen, setAttentionOpen] = usePersisted('attentionOpen', true)
  const flow = useMemo(() => deriveFlow(events), [events])

  if (error && !detail)
    return (
      <Page active="queue">
        <div className="p-8 text-sm">
          <p className="text-coral-700">Could not load {dealId}: {error}</p>
          <a className="font-semibold underline underline-offset-4" href="#/">Back to the queue</a>
        </div>
      </Page>
    )
  if (!detail)
    return (
      <Page active="queue">
        <div className="p-8 text-sm text-slate-600">Loading {dealId}…</div>
      </Page>
    )

  const { status } = detail
  const hasResult = !!(detail.deal && detail.result)
  const active = resolveTab(tab, hasResult)
  const bust = `${status.deal_version}-${events.filter((e) => e.type === 'memo.rendered' || e.type === 'underwriting.completed').length}`
  const showAttention = hasResult && attentionOpen && (active === 'memo' || active === 'numbers')

  const viewSource = (doc: string, locator: string) => {
    setFocus({ doc, locator })
    navigate(`deals/${dealId}/files`)
  }

  return (
    <Page active="queue">
      <div className="flex h-full flex-col">
        <DealHeader dealId={dealId} detail={detail} nav={neighbours(rows, dealId)}
          onChanged={reload} onRequestInfo={() => setInfoDraft('')} />
        <SummaryStrip detail={detail} />

        <div className="flex min-h-0 flex-1">
          {chatOpen ? (
            <aside aria-label="Chief chat" className="w-[21rem] shrink-0 border-r border-slate-200 bg-white">
              <ChatPane key={dealId} dealId={dealId} enabled={hasResult} pending={detail.pending_patches}
                onCollapse={() => setChatOpen(false)} />
            </aside>
          ) : (
            <button onClick={() => setChatOpen(true)} aria-label="Open the chief chat"
              className="w-10 shrink-0 border-r border-slate-200 bg-white text-xs font-semibold text-slate-600 hover:text-ink">
              <span className="[writing-mode:vertical-rl]">Chief chat</span>
            </button>
          )}

          <main className="flex min-w-0 flex-1 flex-col">
            <div className="flex items-end border-b border-slate-200 bg-paper px-6 pt-2">
              <Tabs tabs={DEAL_TABS} active={active} idPrefix={ID} label="Deal views"
                onChange={(id) => navigate(`deals/${dealId}/${id}`)} />
              {hasResult && !attentionOpen && (active === 'memo' || active === 'numbers') && (
                <button onClick={() => setAttentionOpen(true)}
                  className="mb-2 ml-auto text-xs font-semibold text-slate-600 underline underline-offset-4 hover:text-ink">
                  Show what needs attention
                </button>
              )}
            </div>
            <div className="flex min-h-0 flex-1">
              <div className="min-w-0 flex-1 bg-paper">
                <TabPanel id="memo" active={active} idPrefix={ID}>
                  <MemoViewer dealId={dealId} bust={bust} />
                </TabPanel>
                <TabPanel id="numbers" active={active} idPrefix={ID}>
                  {detail.deal && detail.result && (
                    <NumbersTab dealId={dealId} deal={detail.deal} result={detail.result} check={detail.check ?? null}
                      events={events} bust={bust} onViewSource={viewSource} />
                  )}
                </TabPanel>
                <TabPanel id="files" active={active} idPrefix={ID}>
                  <FilesTab dealId={dealId} files={detail.files} focus={focus} />
                </TabPanel>
                <TabPanel id="process" active={active} idPrefix={ID}>
                  <ProcessTab flow={flow} events={events} selected={selected} onSelect={setSelected} />
                </TabPanel>
              </div>
              {showAttention && (
                <AttentionPanel detail={detail} onAsk={(q) => setInfoDraft(q)} onHide={() => setAttentionOpen(false)}
                  showKeyNumbers={active === 'memo'} />
              )}
            </div>
          </main>
        </div>
      </div>
      <RequestInfoDialog dealId={dealId} initial={infoDraft} onClose={() => setInfoDraft(null)} />
    </Page>
  )
}
