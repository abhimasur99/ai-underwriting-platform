// A browser smoke test of the demo path on the rebuilt deal page. Local only (not in CI).
//
// Needs the app running (`make dev`) and the demo deals seeded (`make demo`), which resets the
// data this test changes. Run it with `make e2e`.
import { chromium } from 'playwright-core'

const UI = process.env.E2E_UI ?? 'http://localhost:5173'
const API = process.env.E2E_API ?? 'http://localhost:8000'
let failures = 0
const ok = (condition, message) => {
  console.log(condition ? 'PASS' : 'FAIL', message)
  if (!condition) failures += 1
}
const api = async (path, init) => (await fetch(API + path, init)).json()
const post = (path, body) =>
  api(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

const browser = await chromium.launch({ executablePath: process.env.PLAYWRIGHT_CHROMIUM_PATH || undefined })
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } })
const problems = []
page.on('pageerror', (e) => problems.push(String(e)))
page.on('console', (m) => m.type() === 'error' && problems.push(m.text().slice(0, 200)))
const go = async (hash, wait = 1200) => {
  await page.goto(`${UI}/#/${hash}`)
  await page.waitForTimeout(wait)
}
const tab = () => page.locator('[role=tab][aria-selected=true]').innerText()

// the queue says what needs the reviewer first
await go('')
ok((await page.locator('tbody tr').count()) >= 10, 'the queue lists the seeded deals')
ok((await page.locator('text=Your review').count()) >= 1, 'the queue shows a Next action')

// tabs: default, keyboard, URL, old links
await go('deals/D-0045')
ok((await tab()) === 'Memo', 'a deal opens on the memo')
await page.focus('[role=tab][aria-selected=true]')
await page.keyboard.press('ArrowRight')
await page.waitForTimeout(300)
ok((await tab()) === 'Calculations' && /calculations$/.test(page.url()), 'ArrowRight moves to Calculations and updates the URL')
await page.keyboard.press('End')
await page.waitForTimeout(300)
ok(/process$/.test(page.url()), 'End jumps to the last tab')
await go('deals/D-0045/review', 800)
ok((await tab()) === 'Memo', 'an old /review link still opens the memo')

// a number opens to the line it was read from
await page.click('[role=tab]:has-text("Calculations")')
await page.waitForTimeout(500)
await page.click('text=Loan to cost')
await page.locator('text=View in the document').first().click()
await page.waitForTimeout(900)
ok(/files$/.test(page.url()), 'View in the document lands on the Files tab')
const hit = page.locator('li.bg-amber-50')
ok((await hit.count()) >= 1 && /Loan commitment requested/.test(await hit.first().innerText()),
  'the source line is highlighted')

// the chat collapses, and stays that way
await page.click('button[aria-label="Collapse the chat"]')
await page.reload()
await page.waitForTimeout(1000)
ok((await page.locator('aside[aria-label="Chief chat"]').count()) === 0, 'the chat stays collapsed after a reload')
await page.click('button[aria-label="Open the chief chat"]')

// request info: ask, wait, the sponsor replies, back in review
await go('deals/D-0046/memo')
await page.click('button:has-text("Request info")')
ok((await page.locator('dialog[open]').count()) === 1, 'Request info opens a dialog')
ok(await page.locator('dialog button:has-text("Send to sponsor")').isDisabled(), 'sending needs a note')
await page.fill('dialog textarea', 'Please send the 2025 real estate tax bill.')
await page.click('dialog button:has-text("Send to sponsor")')
await page.waitForTimeout(1200)
ok((await page.locator('header span:has-text("Waiting on sponsor")').count()) >= 1, 'the header says it is waiting on the sponsor')
ok(await page.locator('button:has-text("Approve")').isDisabled(), 'the decision is disabled while waiting')
const status = await api('/api/deals/D-0046/intake-status')
ok(status.message.includes('2025 real estate tax bill'), "the sponsor's chat shows the reviewer's note")
await post('/api/deals/D-0046/chat', { message: 'Attached next week.' })
await page.waitForTimeout(1500)
ok((await page.locator('header span:has-text("Your review")').count()) >= 1, 'a reply returns it to the reviewer')
await page.click('[role=tab]:has-text("Process")')
await page.waitForTimeout(500)
const log = await page.locator('section[aria-label="Deal history"]').innerText()
ok(/Asked the sponsor/.test(log) && /Replied: Attached next week/.test(log), 'the history tells the whole exchange')

// decisions ask before they act
await go('deals/D-0047/memo')
await page.click('button:has-text("Reject")')
ok((await page.locator('text=Reject this deal and close it?').count()) === 1, 'Reject asks for confirmation')
await page.click('button:has-text("Cancel")')
ok(await page.locator('button:has-text("Approve")').isEnabled(), 'cancelling leaves the deal open')

// next needing review is on the right
await go('deals/D-0050/memo', 1000)
const next = page.locator('nav[aria-label=Deals] a:has-text("Next needing review")')
ok((await next.count()) === 1, 'Next needing review is offered')
await next.click()
await page.waitForTimeout(800)
ok(!/D-0050/.test(page.url()), 'and it opens a different deal')

ok(problems.length === 0, `no console errors${problems.length ? `: ${problems.join(' | ')}` : ''}`)
await browser.close()
console.log(failures === 0 ? '\nAll checks passed.' : `\n${failures} check(s) failed.`)
process.exit(failures === 0 ? 0 : 1)
