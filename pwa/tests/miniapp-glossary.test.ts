import { readFileSync } from 'node:fs'
import { expect, it, vi } from 'vitest'
import { fireEvent, waitFor, within } from '@testing-library/dom'

// Exercise the shipped Mini App renderer in a real DOM, including entry by resume.
function renderer(fetch: ReturnType<typeof vi.fn>) {
  const html = readFileSync('../miniapp/index.html', 'utf8')
  const code = html.slice(html.indexOf('function showGlossaryView()'), html.indexOf("modeTopics.addEventListener('click'"))
  const parseTopics = html.slice(html.indexOf('function hasUsableGlossaryTopics('), html.indexOf('function getGlossaryTopicsFromSetupCache('))
  const host = document.createElement('section'); document.body.appendChild(host)
  return new Function('document', 'glossaryFetch', 'host', `
    let glossaryRenderRevision = 0, glossarySavedState = null, glossaryLastSessionId = null, glossaryTopicsCache = [];
    const glossaryView = host, runnerState = document.createElement('p'), err = document.createElement('p');
    const modeView = {}, form = {}, setupIntro = {}, questionView = {};
    const hideSetupWarning = () => {}, showModeSelection = () => {}, buildMiniappRequestId = () => 'synthetic';
    ${parseTopics}
    ${code}
    return {host, renderGlossaryState, renderGlossaryCounts, renderGlossaryTopics};
  `)(document, fetch, host)
}

const question = { session_id: 'saved', step_id: 1, topic_id: 'memory', topic_title: 'Память',
  order_index: 1, total_questions: 5, term: 'Воспроизведение',
  options: [{option_index: 0, option_text: 'Восстановление материала'}, {option_index: 1, option_text: 'Другой ответ'}] }

it('restores the term, locked options and feedback on direct resume, then advances', async () => {
  const fetch = vi.fn().mockResolvedValue({resp: {ok: true}, data: {ok: true, glossary_state: {
    state: 'in_progress', session_id: 'saved', current_question: {...question, step_id: 2, order_index: 2, term: 'Узнавание'},
  }}})
  const view = renderer(fetch)
  view.renderGlossaryState({state: 'feedback', session_id: 'saved', current_question: question, feedback: {
    selected_option_index: 1, correct_option_index: 0, selected_option_text: 'Другой ответ',
    correct_option_text: 'Восстановление материала', explanation: 'Сохранённое объяснение', is_correct: false,
  }})
  expect(within(view.host).getByText('Воспроизведение')).toBeVisible()
  expect(within(view.host).getByRole('button', {name: 'Другой ответ'})).toBeDisabled()
  expect(within(view.host).getByRole('button', {name: 'Восстановление материала'})).toHaveClass('answer-correct')
  expect(within(view.host).getAllByRole('button', {name: 'К темам глоссария'})).toHaveLength(1)
  fireEvent.click(within(view.host).getByRole('button', {name: 'Далее'}))
  await waitFor(() => expect(within(view.host).getByText('Узнавание')).toBeVisible())
  expect(fetch.mock.calls[0][1]).toMatchObject({session_id: 'saved', step_id: 1, action: 'next'})
  expect(within(view.host).queryByText('Пояснение: Сохранённое объяснение')).toBeNull()
  view.host.remove()
})

it('does not let a late setup response replace a newer view or double-submit', async () => {
  let resolve!: (value: unknown) => void
  const fetch = vi.fn().mockImplementation(() => new Promise(done => { resolve = done }))
  const view = renderer(fetch)
  view.renderGlossaryCounts({topic_id: 'memory', title: 'Память'})
  const button = within(view.host).getByRole('button', {name: '5'})
  fireEvent.click(button); fireEvent.click(button)
  expect(fetch).toHaveBeenCalledTimes(1)
  view.renderGlossaryTopics([{topic_id: 'other', title: 'Новая тема'}])
  resolve({resp: {ok: true}, data: {ok: true, glossary_state: {state: 'in_progress', current_question: question}}})
  await Promise.resolve(); await Promise.resolve()
  expect(within(view.host).getByRole('button', {name: 'Новая тема'})).toBeVisible()
  expect(within(view.host).queryByText('Воспроизведение')).toBeNull()
  view.host.remove()
})

it('loads topics from the API after restoring a completed result without a cache', async () => {
  const fetch = vi.fn().mockResolvedValue({resp: {ok: true}, data: {ok: true, glossary: {
    topics: [{topic_id: 'memory', title: 'Память'}],
  }}})
  const view = renderer(fetch)
  view.renderGlossaryState({state: 'completed', session_id: 'saved', result: {score: 4, total_questions: 5}})
  fireEvent.click(within(view.host).getByRole('button', {name: 'К темам глоссария'}))
  await waitFor(() => expect(within(view.host).getByRole('button', {name: 'Память'})).toBeVisible())
  expect(fetch).toHaveBeenCalledWith('/miniapp/setup-options', null, 'synthetic')
  view.host.remove()
})
