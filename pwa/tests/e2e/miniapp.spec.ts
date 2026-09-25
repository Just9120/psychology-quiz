import { expect, test } from '@playwright/test'

const site = 'http://127.0.0.1:4174/'
const question = { session_id: 10, question_id: 20, question_text: 'Первый приём: что сделать?', order_index: 1, total_questions: 1,
  options: [{ option_index: 0, option_text: 'Уточнить запрос' }, { option_index: 1, option_text: 'Поставить диагноз' }] }
const setup = { categories: [{ id: 1, name: 'Кейсы' }], question_count_choices: [5, 'all'], difficulty_choices: ['any'], content_kind_choices: ['theory', 'glossary', 'case'] }

test('built Mini App requires Telegram and keeps initData on the fixed API origin', async ({ page }) => {
  await page.route('https://telegram.org/js/telegram-web-app.js', route => route.abort())
  const requests: string[] = []
  await page.route('https://quiz-api.librechat.online/**', route => { requests.push(route.request().url()); return route.abort() })
  await page.goto(site)
  await expect(page.getByRole('heading', { name: 'Откройте в Telegram' })).toBeVisible()
  expect(requests).toEqual([])
})

test('built Mini App answers a case and shows review on desktop/mobile', async ({ page }) => {
  await page.route('https://telegram.org/js/telegram-web-app.js', route => route.abort())
  await page.addInitScript(() => { (window as typeof window & { Telegram: unknown }).Telegram = { WebApp: { initData: 'synthetic-miniapp-proof', ready() {}, expand() {} } } })
  const paths: string[] = []
  await page.route('https://quiz-api.librechat.online/miniapp/**', async route => {
    const request = route.request()
    if (request.method() === 'OPTIONS') {
      await route.fulfill({ status: 204, headers: { 'Access-Control-Allow-Origin': site.slice(0, -1), 'Access-Control-Allow-Methods': 'GET, POST, OPTIONS', 'Access-Control-Allow-Headers': 'Authorization, Content-Type' } })
      return
    }
    const path = new URL(request.url()).pathname
    paths.push(path)
    if (request.method() === 'POST') expect(request.postData()).toContain('synthetic-miniapp-proof')
    else expect(request.headers().authorization).toBe('tma synthetic-miniapp-proof')
    const payload: Record<string, unknown> = {
      '/miniapp/setup-options': { setup_options: setup },
      '/miniapp/state': { runner_state: { state: 'setup', status: 'setup', session: null } },
      '/miniapp/setup': { runner_state: { state: 'in_progress', status: 'in_progress', session: { session_id: 10 }, current_question: question, progress: { current_question_number: 1, total_questions: 1, answered_count: 0 } } },
      '/miniapp/answer': { runner_state: { state: 'completed', status: 'completed', session: { session_id: 10 }, result: { score: 1, total_questions: 1, percent: 100, summary: '' } }, feedback: { question_id: 20, selected_option_index: 0, selected_option_text: 'Уточнить запрос', correct_option_index: 0, correct_option_text: 'Уточнить запрос', is_correct: true, explanation: 'Нужно уточнить запрос.', case_review: { approach: 'Этический', conditions: ['Согласие'], ambiguity: 'Контекст важен', option_rationales: ['Уточнить запрос', 'Не ставить диагноз'] } } },
    }
    expect(payload[path]).toBeDefined()
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true, ...(payload[path] as object) }), headers: { 'Access-Control-Allow-Origin': site.slice(0, -1) } })
  })
  await page.goto(site)
  await expect(page.getByRole('heading', { name: 'Что изучим сегодня?' })).toBeVisible()
  await page.getByRole('radio', { name: /Кейсы/ }).check()
  await page.getByRole('button', { name: 'Начать квиз' }).click()
  await expect(page.getByRole('heading', { name: 'Первый приём: что сделать?' })).toBeVisible()
  await page.getByRole('radio', { name: /Уточнить запрос/ }).check()
  await page.getByRole('button', { name: 'Проверить ответ' }).click()
  await expect(page.getByRole('heading', { name: 'Разбор кейса' })).toBeVisible()
  await expect(page.getByText('Контекст важен')).toBeVisible()
  expect(paths).toEqual(['/miniapp/setup-options', '/miniapp/state', '/miniapp/setup', '/miniapp/answer'])
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})
