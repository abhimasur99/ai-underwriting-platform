import { useEffect, useState } from 'react'

/** A tiny hash router: "#/deals/D-0001/review" -> ["deals", "D-0001", "review"]. */
function parse(): string[] {
  const hash = window.location.hash.replace(/^#\/?/, '')
  return hash.split('/').filter(Boolean).map(decodeURIComponent)
}

export function useRoute(): string[] {
  const [route, setRoute] = useState(parse)
  useEffect(() => {
    const on = () => setRoute(parse())
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])
  return route
}

export function navigate(path: string, replace = false) {
  const url = `#/${path.replace(/^\/+/, '')}`
  if (replace) {
    window.history.replaceState(null, '', url)
    window.dispatchEvent(new HashChangeEvent('hashchange'))
  } else {
    window.location.hash = url
  }
}
