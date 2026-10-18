import { afterEach, expect, it } from 'vitest'
import { readRoute, writeRoute } from '../src/navigation'
import { takeMailProof } from '../src/proof'
afterEach(() => window.history.replaceState(null, '', '/'))
it('preserves a public deep link through proof processing and filters unknown navigation fields', () => {
  window.history.replaceState(null, '', '/#/literature?book=public-work&q=Картер&token=not-a-proof')
  expect(takeMailProof()).toBeNull()
  expect(readRoute()?.view).toBe('literature')
  expect(readRoute()?.params.get('book')).toBe('public-work')
  expect(readRoute()?.params.has('token')).toBe(false)
  expect(readRoute()?.params.get('q')).toBe('Картер')
})
it('rejects unknown sections and never interprets mail proofs as destinations', () => {
  window.history.replaceState(null, '', '/#verify=' + 'a'.repeat(43))
  expect(readRoute()).toBeNull()
  expect(takeMailProof()?.purpose).toBe('verify')
  expect(window.location.hash).toBe('')
  window.history.replaceState(null, '', '/#/https://foreign.test')
  expect(readRoute()).toBeNull()
  writeRoute('progress')
  expect(window.location.hash).toBe('#/progress')
})
