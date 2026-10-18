export type Section = 'quiz' | 'setup' | 'homework' | 'account' | 'progress' | 'errors' | 'glossary' | 'literature' | 'learning' | 'ownerStats' | 'ownerContent'
const sections = new Set<Section>(['quiz', 'setup', 'homework', 'account', 'progress', 'errors', 'glossary', 'literature', 'learning', 'ownerStats', 'ownerContent'])
export type Route = { view: Section; params: URLSearchParams }
export function readRoute(): Route | null {
  const match = /^#\/([^?]+)(?:\?(.*))?$/.exec(window.location.hash)
  if (!match || !sections.has(match[1] as Section)) return null
  const params = new URLSearchParams(match[2] ?? '')
  return { view: match[1] as Section, params: new URLSearchParams([...params].filter(([key]) => ['book', 'entry', 'topic', 'status', 'q'].includes(key))) }
}
export function writeRoute(view: Section, params = new URLSearchParams(), replace = false) {
  const query = params.toString()
  const hash = `#/${view}${query ? `?${query}` : ''}`
  if (window.location.hash === hash) return
  // History stores only public navigation; never cache personal API payloads or authentication proofs.
  window.history[replace ? 'replaceState' : 'pushState'](null, '', hash)
}
