import { createHmac } from 'node:crypto'
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

test('Mini App recovers its setup screen after the first server load fails', async ({ page }) => {
  await page.route('https://telegram.org/js/telegram-web-app.js', route => route.abort())
  await page.addInitScript(() => { (window as typeof window & { Telegram: unknown }).Telegram = { WebApp: { initData: 'synthetic-miniapp-proof', ready() {}, expand() {} } } })
  let failedOnce = false
  await page.route('https://quiz-api.librechat.online/miniapp/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (route.request().method() === 'OPTIONS') {
      await route.fulfill({ status: 204, headers: { 'Access-Control-Allow-Origin': site.slice(0, -1), 'Access-Control-Allow-Methods': 'GET, POST, OPTIONS', 'Access-Control-Allow-Headers': 'Authorization, Content-Type' } })
    } else if (path === '/miniapp/setup-options' && !failedOnce) {
      failedOnce = true
      await route.abort('failed')
    } else {
      const payload = path === '/miniapp/setup-options' ? { setup_options: setup }
        : { runner_state: { state: 'setup', status: 'setup', session: null } }
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true, ...payload }), headers: { 'Access-Control-Allow-Origin': site.slice(0, -1) } })
    }
  })
  await page.goto(site)
  await expect(page.getByRole('alert')).toContainText('Ответ сервера не получен')
  await page.getByRole('button', { name: 'Повторить загрузку' }).click()
  await expect(page.getByRole('heading', { name: 'Что изучим сегодня?' })).toBeVisible()
  expect(failedOnce).toBe(true)
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

test('Telegram Mini App selects mixed glossary topics and shows API feedback', async ({ page }) => {
  await page.route('https://telegram.org/js/telegram-web-app.js', route => route.abort())
  await page.addInitScript(() => { (window as typeof window & { Telegram: unknown }).Telegram = { WebApp: { initData: 'synthetic-miniapp-proof', ready() {}, expand() {} } } })
  const topicIds = ['memory', 'attention']
  let setupPayload: unknown = null
  const currentQuestion = { session_id: 'glossary-one', step_id: 1, topic_id: 'attention', topic_title: 'Внимание',
    order_index: 1, total_questions: 5, term: 'Концентрация',
    options: [{ option_index: 0, option_text: 'Сосредоточение' }, { option_index: 1, option_text: 'Забывание' }] }
  await page.route('https://quiz-api.librechat.online/miniapp/**', async route => {
    const request = route.request()
    if (request.method() === 'OPTIONS') {
      await route.fulfill({ status: 204, headers: { 'Access-Control-Allow-Origin': site.slice(0, -1),
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS', 'Access-Control-Allow-Headers': 'Authorization, Content-Type' } })
      return
    }
    const path = new URL(request.url()).pathname
    const body = request.method() === 'POST' ? request.postDataJSON() : null
    if (body) expect(body.init_data).toBe('synthetic-miniapp-proof')
    const payload: Record<string, unknown> = {
      '/miniapp/setup-options': { setup_options: setup },
      '/miniapp/state': { runner_state: { state: 'setup', status: 'setup', session: null } },
      '/miniapp/glossary/topics': { glossary: { topics: [
        { topic_id: 'memory', title: 'Память', available_count: 5 },
        { topic_id: 'attention', title: 'Внимание', available_count: 5 },
      ] } },
      '/miniapp/answer': { glossary_state: { state: 'idle' } },
      '/miniapp/glossary/start': { glossary_state: { state: 'in_progress', session_id: 'glossary-one',
        topic_id: '__mixed__', topic_title: 'Несколько тем', topic_ids: topicIds,
        current_question: currentQuestion } },
      '/miniapp/glossary/answer': { glossary_state: { state: 'feedback', feedback: { step_id: 1,
        is_correct: true, selected_option_index: 0, selected_option_text: 'Сосредоточение',
        correct_option_index: 0, correct_option_text: 'Сосредоточение', explanation: 'Направленность внимания.',
        answered_count: 1, total_questions: 5, has_next: true } } },
    }
    if (path === '/miniapp/glossary/start') setupPayload = body.payload
    expect(payload[path]).toBeDefined()
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true, ...(payload[path] as object) }),
      headers: { 'Access-Control-Allow-Origin': site.slice(0, -1) } })
  })
  await page.goto(site)
  await page.getByRole('button', { name: 'Глоссарий' }).click()
  await page.getByRole('combobox', { name: 'Режим', exact: true }).selectOption('mix')
  await page.getByRole('checkbox', { name: /Память/ }).check()
  await page.getByRole('checkbox', { name: /Внимание/ }).check()
  await page.getByRole('button', { name: 'Начать тест по терминам' }).click()
  expect(setupPayload).toMatchObject({ topic_id: topicIds, question_count: 5 })
  await expect(page.getByRole('heading', { name: 'Что означает «Концентрация»?' })).toBeVisible()
  await page.getByRole('radio', { name: /Сосредоточение/ }).check()
  await page.getByRole('button', { name: 'Проверить определение' }).click()
  await expect(page.getByText('Направленность внимания.')).toBeVisible()
})

for (const sameSession of [true, false]) {
  test(`lost Mini App reply ${sameSession ? 'recovers the committed answer' : 'does not attach another attempt’s feedback'}`, async ({ page }) => {
    await page.route('https://telegram.org/js/telegram-web-app.js', route => route.abort())
    await page.addInitScript(() => { (window as typeof window & { Telegram: unknown }).Telegram = { WebApp: { initData: 'synthetic-miniapp-proof' } } })
    let lost = false
    let answers = 0
    await page.route('https://quiz-api.librechat.online/miniapp/**', async route => {
      const request = route.request()
      if (request.method() === 'OPTIONS') {
        await route.fulfill({ status: 204, headers: { 'Access-Control-Allow-Origin': site.slice(0, -1), 'Access-Control-Allow-Methods': 'GET, POST, OPTIONS', 'Access-Control-Allow-Headers': 'Authorization, Content-Type' } })
        return
      }
      const path = new URL(request.url()).pathname
      if (path === '/miniapp/answer') {
        answers++
        lost = true
        await route.abort('failed')
        return
      }
      const runner = lost
        ? { state: 'completed', status: 'completed', session: { session_id: sameSession ? 10 : 11 }, result: { score: 1, total_questions: 1, percent: 100, summary: '' } }
        : { state: 'setup', status: 'setup', session: null }
      const feedback = { question_id: 20, selected_option_index: 0, selected_option_text: 'Уточнить запрос', correct_option_index: 0,
        correct_option_text: 'Уточнить запрос', is_correct: true, explanation: 'Нужно уточнить запрос.',
        case_review: { approach: 'Этический', conditions: ['Согласие'], ambiguity: 'Контекст важен', option_rationales: ['Уточнить запрос', 'Не ставить диагноз'] } }
      const payload = path === '/miniapp/setup-options' ? { setup_options: setup }
        : path === '/miniapp/setup' ? { runner_state: { state: 'in_progress', status: 'in_progress', session: { session_id: 10 }, current_question: question, progress: { current_question_number: 1, total_questions: 1, answered_count: 0 } } }
          : { runner_state: runner, ...(lost ? { recent_answer_feedback: feedback } : {}) }
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true, ...payload }),
        headers: { 'Access-Control-Allow-Origin': site.slice(0, -1) } })
    })
    await page.goto(site)
    await page.getByRole('radio', { name: /Кейсы/ }).check()
    await page.getByRole('button', { name: 'Начать квиз' }).click()
    await page.getByRole('radio', { name: /Уточнить запрос/ }).check()
    await page.getByRole('button', { name: 'Проверить ответ' }).click()
    if (sameSession) {
      await expect(page.getByRole('heading', { name: 'Разбор кейса' })).toBeVisible()
      await expect(page.getByText('Контекст важен')).toBeVisible()
    } else {
      await expect(page.getByRole('alert')).toContainText('Ответ сервера не получен')
      await expect(page.getByRole('heading', { name: 'Разбор кейса' })).not.toBeVisible()
    }
    expect(answers).toBe(1)
  })
}


test('built Mini App opens book offers externally without passing Telegram proof', async ({ page }) => {
  await page.route('https://telegram.org/js/telegram-web-app.js', route => route.abort())
  await page.addInitScript(() => { (window as typeof window & { Telegram: unknown }).Telegram = { WebApp: { initData: 'synthetic-miniapp-proof', ready() {}, expand() {} } } })
  const offers = [{ format: 'text', provider: 'Провайдер', url: 'https://books.example.test/text', access: 'provider_terms', checked_at: '2026-09-30' },
                  { format: 'audio', provider: 'Провайдер', url: 'https://books.example.test/audio', access: 'provider_terms', checked_at: '2026-09-30' }]
  await page.route('https://quiz-api.librechat.online/miniapp/**', async route => {
    const path = new URL(route.request().url()).pathname
    const payload: Record<string, object> = {
      '/miniapp/setup-options': { setup_options: setup },
      '/miniapp/state': { runner_state: { state: 'setup', status: 'setup', session: null } },
      '/miniapp/literature/topics': { literature_topics: [{ topic_id: 'one', title: 'Тема', module: 'module1' }] },
      '/miniapp/literature/items': { literature_items: [{ id: 'book', work_id: 'work', title: 'Учебная книга', topic_id: 'one', access_links: offers, user_state: null }] },
    }
    expect(payload[path]).toBeDefined()
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ ok: true, ...payload[path] }), headers: { 'Access-Control-Allow-Origin': site.slice(0, -1) } })
  })
  await page.goto(site)
  await page.getByRole('button', { name: 'Литература', exact: true }).click()
  await page.getByRole('button', { name: 'Учебная книга', exact: true }).click()
  await expect(page.getByText('Доступ и совпадение издания уточняются у провайдера.')).toBeVisible()
  for (const offer of offers) {
    await page.context().route(offer.url, async route => {
      expect(route.request().url()).not.toContain('synthetic-miniapp-proof')
      expect(route.request().headers().authorization).toBeUndefined()
      expect(route.request().headers().cookie).toBeUndefined()
      await route.fulfill({ contentType: 'text/html', body: '<title>External provider fixture</title>' })
    })
    const link = page.getByRole('link', { name: `${offer.format === 'text' ? 'Текст' : 'Аудио'} · ${offer.provider}`, exact: true })
    await expect(link).toHaveAttribute('rel', 'noopener noreferrer')
    const opened = page.context().waitForEvent('page')
    await link.click()
    const provider = await opened
    await expect(provider).toHaveURL(offer.url)
    expect(await provider.evaluate(() => window.opener)).toBeNull()
    await provider.close()
    await page.context().unroute(offer.url)
  }
  await expect(page.getByRole('combobox', { name: 'Статус', exact: true })).toHaveValue('not_started')
})


test('Mini App reading next step persists against the real local backend', async ({ page, request }) => {
  const backend = 'http://127.0.0.1:8085'
  expect((await request.post(backend + '/__test/reset', { data: { seed: true } })).ok()).toBe(true)
  const proof = new URLSearchParams({ auth_date: String(Math.floor(Date.now() / 1000)),
    user: JSON.stringify({ id: 4242, first_name: 'Synthetic learner' }) })
  const secret = createHmac('sha256', 'WebAppData').update('123:synthetic-e2e').digest()
  const check = [...proof.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([key, value]) => `${key}=${value}`).join('\n')
  proof.set('hash', createHmac('sha256', secret).update(check).digest('hex'))
  const initData = proof.toString()
  await page.route('https://telegram.org/js/telegram-web-app.js', route => route.abort())
  await page.addInitScript(value => {
    (window as typeof window & { Telegram: unknown }).Telegram = {
      WebApp: { initData: value, ready() {}, expand() {} },
    }
  }, initData)
  await page.route('https://quiz-api.librechat.online/miniapp/**', async route => {
    if (route.request().method() === 'OPTIONS') {
      await route.fulfill({ status: 204, headers: { 'Access-Control-Allow-Origin': site.slice(0, -1),
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS', 'Access-Control-Allow-Headers': 'Authorization, Content-Type' } })
      return
    }
    const url = new URL(route.request().url())
    const response = await route.fetch({ url: backend + url.pathname + url.search })
    await route.fulfill({ response, headers: { ...response.headers(), 'Access-Control-Allow-Origin': site.slice(0, -1) } })
  })
  async function openReading() {
    await page.goto(site)
    await expect(page.getByRole('heading', { name: 'Что изучим сегодня?' })).toBeVisible()
    await page.getByRole('button', { name: 'Литература', exact: true }).click()
  }
  await openReading()
  const next = page.getByRole('region', { name: 'Следующий шаг чтения' })
  await next.getByRole('button', { name: /^Начать «/ }).click()
  const title = await page.locator('.literature-detail h2').innerText()
  await page.getByRole('combobox', { name: 'Статус', exact: true }).selectOption('in_progress')
  await page.getByRole('button', { name: 'Сохранить чтение' }).click()
  await expect(page.getByText('Отметка сохранена.')).toBeVisible()
  await openReading()
  await next.getByRole('button', { name: `Продолжить «${title}»`, exact: true }).click()
  await expect(page.getByRole('combobox', { name: 'Статус', exact: true })).toHaveValue('in_progress')
  await page.getByRole('combobox', { name: 'Статус', exact: true }).selectOption('read')
  await page.getByRole('button', { name: 'Сохранить чтение' }).click()
  await expect(page.getByText('Отметка сохранена.')).toBeVisible()
  await openReading()
  await expect(next.getByRole('button', { name: /^Начать «/ })).toBeVisible()
  await expect(next).not.toContainText(title)
  const response = await request.get(backend + '/miniapp/literature/items', { headers: { Authorization: `tma ${initData}` } })
  expect(response.ok()).toBe(true)
  const result = await response.json() as { literature_items: { title: string; work_id: string; user_state: { reading_status: string } | null }[] }
  const selected = result.literature_items.find(entry => entry.title === title)!
  const aliases = result.literature_items.filter(entry => entry.work_id === selected.work_id)
  expect(aliases.length).toBeGreaterThan(0)
  expect(aliases.every(entry => entry.user_state?.reading_status === 'read')).toBe(true)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})
