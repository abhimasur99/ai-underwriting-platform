import DealPage from './features/deal/DealPage'
import Chat from './features/intake/Chat'
import Queue from './features/queue/Queue'
import { useRoute } from './lib/router'

// Routes: #/ (queue), #/chat[/D-0001] (external intake), #/deals/D-0001[/flow|review].
export default function App() {
  const [a, b, c] = useRoute()
  if (a === 'chat') return <Chat key={b ?? 'new'} dealId={b ?? null} />
  if (a === 'deals' && b) return <DealPage key={b} dealId={b} tab={c} />
  return <Queue />
}
