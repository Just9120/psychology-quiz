import { readFileSync } from 'node:fs'
import { fireEvent, waitFor, within } from '@testing-library/dom'
import { expect, it, vi } from 'vitest'

const html = readFileSync('../miniapp/index.html', 'utf8')
const code = html.slice(html.indexOf('function showLearningView('), html.indexOf("modeTopics.addEventListener('click'"))

function screenFor(fetch: ReturnType<typeof vi.fn>) {
  const host = document.createElement('section')
  document.body.appendChild(host)
  const mode = document.createElement('button')
  const runner = document.createElement('p')
  host.appendChild(mode); host.appendChild(runner)
  const handlers = new Function('document', 'host', 'mode', 'runner', 'fetch', `
    const learningView = document.createElement('div'), modeLearning = mode, runnerState = runner;
    host.appendChild(learningView);
    const modeView = {}, form = {}, setupIntro = {}, questionView = {}, glossaryView = {}, literatureView = {};
    const apiBase = 'https://api.example.test', tg = {initData: 'synthetic'};
    const glossaryFetch = fetch, buildMiniappRequestId = () => 'synthetic';
    const hideSetupWarning = () => {}, renderRunnerState = () => {}, renderGlossaryState = () => {};
    let glossarySavedState = null;
    ${code}
    return {learningView, loadLearningView};
  `)(document, host, mode, runner, fetch) as { learningView: HTMLElement; loadLearningView: () => Promise<void> }
  return { ...handlers, host, mode, runner }
}

const reply = (data: object, status = 200) => ({ resp: { ok: status === 200, status }, data })

it('shows personal queue, conservative mastery, goals and achievements from verified API', async () => {
  const fetch = vi.fn(async (path: string) => {
    if (path.endsWith('/review')) return reply({ ok: true, due_count: 0, items: [] })
    if (path.endsWith('/mastery')) return reply({ ok: true, questions: { mastered_count: 0, assessed_count: 1 }, terms: { mastered_count: 0, assessed_count: 0 } })
    if (path.endsWith('/goals')) return reply({ ok: true, week_start: '2026-09-21', goals: [{ goal_kind: 'study', completed: 1, weekly_target: 2 }] })
    return reply({ ok: true, achievements: [] })
  })
  const view = screenFor(fetch)
  fireEvent.click(view.mode)
  await waitFor(() => expect(within(view.learningView).getByText(/Сегодня к повторению: 0/)).toBeVisible())
  expect(within(view.learningView).getByText(/Иначе данных недостаточно/)).toBeVisible()
  expect(within(view.learningView).getByText(/Пока нет достижений/)).toBeVisible()
})

it('does not replace an active attempt without explicit confirmation', async () => {
  const fetch = vi.fn(async (path: string, payload: object | null) => {
    if (path.endsWith('/learning/review')) return reply({ ok: true, due_count: 1, items: [{ kind: 'quiz', is_due: true, topic: 'Кейсы' }] })
    if (path.endsWith('/learning/mastery')) return reply({ ok: true, questions: { mastered_count: 0, assessed_count: 0 }, terms: { mastered_count: 0, assessed_count: 0 } })
    if (path.endsWith('/learning/goals')) return reply({ ok: true, week_start: '2026-09-21', goals: [] })
    if (path.endsWith('/learning/achievements')) return reply({ ok: true, achievements: [] })
    if (path.endsWith('/miniapp/state')) return reply({ ok: true, runner_state: { session: { session_id: 12 } } })
    if (path.endsWith('/learning/review-start')) return reply({ ok: false, error: 'active_attempt' }, 409)
    throw Error(`unexpected ${path} ${String(payload)}`)
  })
  const view = screenFor(fetch)
  await view.loadLearningView()
  fireEvent.click(within(view.learningView).getByRole('button', { name: 'Повторить вопросы' }))
  await waitFor(() => expect(within(view.learningView).getByRole('button', { name: 'Подтвердить замену' })).toBeVisible())
  expect(fetch).toHaveBeenCalledWith('/miniapp/learning/review-start', { expected_session_id: 12, replace_active: false, question_count: 5 }, 'synthetic')
  expect(fetch).not.toHaveBeenCalledWith('/miniapp/learning/review-start', { expected_session_id: 12, replace_active: true, question_count: 5 }, 'synthetic')
})
