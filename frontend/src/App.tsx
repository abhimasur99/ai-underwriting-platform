import Chat from './pages/Chat'
import Queue from './pages/Queue'
import Workspace from './pages/Workspace'
import { useRoute } from './lib/router'

// Routes: #/ (queue), #/chat[/D-0001] (external intake), #/deals/D-0001[/flow|review].
export default function App() {
  const [a, b, c] = useRoute()
  if (a === 'chat') return <Chat key={b ?? 'new'} dealId={b ?? null} />
  if (a === 'deals' && b) return <Workspace key={b} dealId={b} tab={c} />
  return <Queue />
}
