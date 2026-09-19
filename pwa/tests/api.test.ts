import { describe, expect, it, vi } from 'vitest'
import { api, ApiError, errorMessage, request } from '../src/api'
import { takeMailProof } from '../src/proof'

describe('private transport', () => {
  it('pins destination/credentials, rejects redirects and forwards only in-memory CSRF', async () => {
    const fetcher = vi.fn().mockImplementation(async () => new Response(JSON.stringify({ ok: true, csrf_token: 'proof' })))
    vi.stubGlobal('fetch', fetcher)
    await api.me(); await api.newIdentity()
    expect(fetcher.mock.calls[1]).toEqual(['/web/identity/new', expect.objectContaining({ method: 'POST', credentials: 'same-origin', redirect: 'error', cache: 'no-store', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': 'proof' } })])
    await expect(request('https://outside.test')).rejects.toMatchObject({ code: 'invalid_destination' })
    expect(fetcher).toHaveBeenCalledTimes(2)
    fetcher.mockResolvedValueOnce(new Response('{"ok":false,"error":"unauthorized"}', { status: 401 }))
    await expect(api.me()).rejects.toMatchObject({ status: 401 })
    await api.newIdentity()
    expect(fetcher.mock.lastCall?.[1].headers).not.toHaveProperty('X-CSRF-Token')
  })
  it('never displays server diagnostics or arbitrary failures', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('SMTP private diagnostics', { status: 500 })))
    await expect(api.state()).rejects.toBeInstanceOf(ApiError)
    expect(errorMessage(new ApiError('private@example.test'))).not.toContain('private')
  })
})

describe('mail proof', () => {
  it('removes fragment and query before consuming it, without persistent storage', () => {
    history.replaceState(null, '', '/?tracking=unwanted#verify=' + 'a'.repeat(43))
    expect(takeMailProof()).toEqual({ purpose: 'verify', token: 'a'.repeat(43) })
    expect(location.href).not.toContain('verify')
    expect(location.search).toBe('')
    expect(takeMailProof()).toBeNull()
    expect(localStorage.length + sessionStorage.length).toBe(0)
  })
  it('discards malformed proof without reflecting it', () => {
    history.replaceState(null, '', '/#recover=unsafe')
    expect(takeMailProof()).toBeNull()
    expect(location.hash).toBe('')
  })
})
