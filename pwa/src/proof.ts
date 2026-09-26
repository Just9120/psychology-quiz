import type { MailProof } from './types'

export function takeInvitation(): string | null {
  if (!window.location.hash.startsWith('#invite=')) return null
  const fragment = window.location.hash.slice(1)
  window.history.replaceState(null, '', window.location.pathname)
  const token = new URLSearchParams(fragment).get('invite')
  return token && /^[A-Za-z0-9_-]{43}$/.test(token) ? token : null
}

// Run before rendering or fetching anything. No storage, analytics or query transport.
export function takeMailProof(): MailProof | null {
  const fragment = window.location.hash.slice(1)
  if (!fragment) return null
  window.history.replaceState(null, '', window.location.pathname)
  const params = new URLSearchParams(fragment)
  for (const purpose of ['verify', 'recover'] as const) {
    const token = params.get(purpose)
    if (token && /^[A-Za-z0-9_-]{43}$/.test(token)) return { purpose, token }
  }
  return null
}
