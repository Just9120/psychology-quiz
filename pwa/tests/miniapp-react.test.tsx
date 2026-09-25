import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MiniApp } from '../src/miniapp/MiniApp'
import { miniRequest } from '../src/miniapp/api'

const setupOptions = { categories: [{ id: 1, name: 'Кейсы' }], question_count_choices: [5, 'all'], difficulty_choices: ['any'], content_kind_choices: ['theory', 'glossary', 'case'] }
const question = { session_id: 10, question_id: 20, question_text: 'Что делать на первой консультации?', order_index: 1, total_questions: 1, options: [{ option_index: 0, option_text: 'Спросить о запросе' }, { option_index: 1, option_text: 'Дать диагноз' }] }
const idle = { state: 'setup', status: 'setup', session: null }
const running = { state: 'in_progress', status: 'in_progress', session: { session_id: 10 }, current_question: question, progress: { current_question_number: 1, total_questions: 1, answered_count: 0 } }
const completed = { state: 'completed', status: 'completed', session: { session_id: 10 }, result: { score: 1, total_questions: 1, percent: 100, summary: '' } }
const feedback = { question_id: 20, selected_option_index: 0, selected_option_text: 'Спросить о запросе', correct_option_index: 0, correct_option_text: 'Спросить о запросе', is_correct: true, explanation: 'Нужно уточнить запрос.', case_review: { approach: 'Этический подход', conditions: ['Согласие'], ambiguity: 'Контекст важен', option_rationales: ['Уточнить запрос', 'Не ставить диагноз'] } }
const reply = (data: unknown) => new Response(JSON.stringify(data), { status: 200, headers: { 'Content-Type': 'application/json' } })

beforeEach(() => { window.Telegram = { WebApp: { initData: 'verified-test-payload', ready: vi.fn(), expand: vi.fn() } } })
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); delete window.Telegram })

test('Telegram Mini App loads shared quiz, checks a case and shows its rationale', async () => {
  const calls: { path: string; initData: string }[] = []
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, options?: RequestInit) => {
    const path = new URL(String(input)).pathname
    calls.push({ path, initData: String((options?.headers as Record<string, string> | undefined)?.Authorization ?? options?.body) })
    if (path.endsWith('/setup-options')) return reply({ ok: true, setup_options: setupOptions })
    if (path.endsWith('/state')) return reply({ ok: true, runner_state: idle })
    if (path.endsWith('/setup')) return reply({ ok: true, runner_state: running })
    if (path.endsWith('/answer')) return reply({ ok: true, runner_state: completed, feedback })
    throw Error(`unexpected route ${path}`)
  }))
  render(<MiniApp />)
  await screen.findByRole('heading', { name: 'Что изучим сегодня?' })
  fireEvent.click(screen.getByRole('radio', { name: 'Кейсы' }))
  fireEvent.click(screen.getByRole('button', { name: 'Начать квиз' }))
  await screen.findByText('Что делать на первой консультации?')
  fireEvent.click(screen.getByRole('radio', { name: /Спросить о запросе/ }))
  fireEvent.click(screen.getByRole('button', { name: 'Проверить ответ' }))
  await screen.findByRole('heading', { name: 'Разбор кейса' })
  expect(screen.getByText('Контекст важен')).toBeInTheDocument()
  expect(calls.map(call => call.path)).toEqual(['/miniapp/setup-options', '/miniapp/state', '/miniapp/setup', '/miniapp/answer'])
  expect(calls.every(call => call.initData.includes('verified-test-payload'))).toBe(true)
})

test('missing Telegram initData does not make a network request', async () => {
  delete window.Telegram
  const fetch = vi.fn()
  vi.stubGlobal('fetch', fetch)
  render(<MiniApp />)
  expect(screen.getByRole('heading', { name: 'Откройте в Telegram' })).toBeInTheDocument()
  await expect(miniRequest('state')).rejects.toMatchObject({ code: 'telegram_required', status: 401 })
  expect(fetch).not.toHaveBeenCalled()
})

test('verified Telegram actor can open review, glossary and literature without PWA e-mail', async () => {
  const seen: string[] = []
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const path = new URL(String(input)).pathname
    seen.push(path)
    const values: Record<string, unknown> = {
      '/miniapp/setup-options': { setup_options: setupOptions },
      '/miniapp/state': { runner_state: idle },
      '/miniapp/learning/review': { today: '2026-09-25', due_count: 0, items: [] },
      '/miniapp/learning/overview': { summary: { attempts: 0, finished: 0, answered: 0, correct: 0, accuracy: null }, topics: [], days: [] },
      '/miniapp/learning/mastery': { questions: { items: [], mastered_count: 0, assessed_count: 0 }, terms: { items: [], mastered_count: 0, assessed_count: 0 } },
      '/miniapp/learning/goals': { week_start: '2026-09-21', week_end_exclusive: '2026-09-28', goals: [{ goal_kind: 'study', weekly_target: null, completed: 0, reached: null }] },
      '/miniapp/learning/achievements': { achievements: [] },
      '/miniapp/answer': { glossary_state: { state: 'idle' } },
      '/miniapp/glossary/topics': { glossary: { topics: [{ topic_id: 'intro', title: 'Введение', available_count: 5 }] } },
      '/miniapp/literature/topics': { literature_topics: [{ topic_id: 'intro', title: 'Введение' }] },
      '/miniapp/literature/items': { literature_items: [{ id: 'book-1', topic_id: 'intro', title: 'Учебный список', authors: ['Автор'] }] },
    }
    if (!values[path]) throw Error(`unexpected route ${path}`)
    return reply({ ok: true, ...(values[path] as object) })
  }))
  render(<MiniApp />)
  await screen.findByRole('heading', { name: 'Что изучим сегодня?' })
  fireEvent.click(screen.getByRole('button', { name: 'Повторение и цели' }))
  await screen.findByRole('heading', { name: 'Повторение и цели' })
  expect(screen.getByText(/Пока нет ответов/)).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Глоссарий' }))
  await screen.findByRole('heading', { name: 'Глоссарий' })
  fireEvent.click(screen.getByRole('button', { name: 'Литература' }))
  await screen.findByRole('heading', { name: 'Литература' })
  expect(screen.getByText('Учебный список')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Мой прогресс' }))
  await screen.findByRole('heading', { name: 'Мой прогресс' })
  expect(screen.getByText(/Истории ответов пока нет/)).toBeInTheDocument()
  expect(seen).toContain('/miniapp/glossary/topics')
  expect(seen).toContain('/miniapp/literature/items')
})
