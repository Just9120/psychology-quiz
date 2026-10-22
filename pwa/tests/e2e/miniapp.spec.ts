import { createHmac } from 'node:crypto'
import { expect, test } from '@playwright/test'

async function chooseMenu(page: import('@playwright/test').Page, field: import('@playwright/test').Locator, value: string) {
  await field.click()
  const options = page.getByRole('option')
  const values = await options.evaluateAll(items => items.map(item => item.getAttribute('data-value')))
  const index = values.indexOf(value)
  expect(index).toBeGreaterThanOrEqual(0)
  await options.nth(index).click()
}

async function navigateMini(page: import('@playwright/test').Page, name: string) {
  const destination = page.getByRole('button', { name, exact: true, includeHidden: true })
  await expect(destination).toBeAttached()
  await expect(destination).toBeEnabled()
  if (!(await destination.isVisible())) await page.getByRole('button', { name: 'Открыть меню', exact: true }).click()
  await destination.click()
  await expect(destination).toHaveAttribute('aria-current', 'page')
}

const site = 'http://127.0.0.1:4174/'
const question = { session_id: 10, question_id: 20, question_text: 'Первый приём: что сделать?', order_index: 1, total_questions: 1,
  options: [{ option_index: 0, option_text: 'Уточнить запрос' }, { option_index: 1, option_text: 'Поставить диагноз' }] }
const setup = { categories: [{ id: 1, name: 'Кейсы' }], question_count_choices: [5, 'all'], difficulty_choices: ['any'], content_kind_choices: ['theory', 'glossary', 'case'] }

test('Mini App compact catalog preserves cold navigation and avoids warm personal refetch', async ({ page, request }) => {
  const backend = 'http://127.0.0.1:8085'
  expect((await request.post(backend + '/__test/reset', { data: { seed: true } })).ok()).toBe(true)
  const proof = new URLSearchParams({ auth_date: String(Math.floor(Date.now() / 1000)), user: JSON.stringify({ id: 4242, first_name: 'Synthetic learner' }) })
  const secret = createHmac('sha256', 'WebAppData').update('123:synthetic-e2e').digest()
  proof.set('hash', createHmac('sha256', secret).update([...proof.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([k, v]) => `${k}=${v}`).join('\n')).digest('hex'))
  await page.route('https://telegram.org/js/telegram-web-app.js', route => route.abort())
  await page.addInitScript(initData => { window.Telegram = { WebApp: { initData, ready() {}, expand() {} } } }, proof.toString())
  const samples: { bytes: number; api_ms: number; cold_ui_ms: number; warm_ui_ms: number; encoding: string }[] = []
  let catalogCalls = 0
  await page.route('https://quiz-api.librechat.online/miniapp/**', async route => {
    if (route.request().method() === 'OPTIONS') return route.fulfill({ status: 204, headers: { 'Access-Control-Allow-Origin': site.slice(0, -1), 'Access-Control-Allow-Methods': 'GET, POST, OPTIONS', 'Access-Control-Allow-Headers': 'Authorization, Content-Type' } })
    const url = new URL(route.request().url()), started = performance.now()
    const response = await route.fetch({ url: backend + url.pathname + url.search })
    if (url.pathname.endsWith('/catalog-compact')) {
      catalogCalls++
      samples.push({ bytes: (await response.body()).length, api_ms: performance.now() - started, cold_ui_ms: 0, warm_ui_ms: 0, encoding: response.headers()['content-encoding'] ?? 'identity' })
    }
    await route.fulfill({ response, headers: { ...response.headers(), 'Access-Control-Allow-Origin': site.slice(0, -1) } })
  })
  for (let index = 0; index < 3; index++) {
    await page.goto(site)
    await expect(page.getByRole('heading', { name: 'Что изучим сегодня?' })).toBeVisible()
    const cold = performance.now()
    await navigateMini(page, 'Литература')
    await expect(page.locator('.literature-card').first()).toBeVisible()
    samples[index].cold_ui_ms = performance.now() - cold
    await navigateMini(page, 'Квиз')
    const warm = performance.now()
    await navigateMini(page, 'Литература')
    await expect(page.locator('.literature-card').first()).toBeVisible()
    samples[index].warm_ui_ms = performance.now() - warm
    expect(catalogCalls).toBe(index + 1)
  }
  const flat = await request.get(backend + '/miniapp/literature/items', { headers: { Authorization: 'tma ' + proof.toString() } })
  expect(flat.ok()).toBe(true)
  const flatBytes = (await flat.body()).length
  expect(samples.every(sample => sample.bytes < flatBytes)).toBe(true)
  console.log('CATALOG_SAMPLES_LOCAL_SYNTHETIC', JSON.stringify({ flat_bytes: flatBytes, samples }))
})

test('built Mini App requires Telegram and keeps initData on the fixed API origin', async ({ page }) => {
  await page.route('https://telegram.org/js/telegram-web-app.js', route => route.abort())
  const requests: string[] = []
  await page.route('https://quiz-api.librechat.online/**', route => { requests.push(route.request().url()); return route.abort() })
  await page.goto(site)
  await expect(page.getByRole('heading', { name: 'Откройте в Telegram' })).toBeVisible()
  expect(requests).toEqual([])
  await expect(page.getByRole('link', { name: 'Открыть бота в Telegram' })).toHaveAttribute('href', 'https://t.me/psychologyquiz1_bot')
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
  await navigateMini(page, 'Глоссарий')
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
      '/miniapp/literature/catalog-compact': { topics: [{ topic_id: 'one', title: 'Тема', module: 'module1' }], works: [{ work_id: 'work', title: 'Учебная книга', access_links: offers, entries: [{ id: 'book', topic_id: 'one', user_state: null }] }] },
    }
    expect(payload[path]).toBeDefined()
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ ok: true, ...payload[path] }), headers: { 'Access-Control-Allow-Origin': site.slice(0, -1) } })
  })
  await page.goto(site)
  await navigateMini(page, 'Литература')
  await page.getByRole('button', { name: 'Учебная книга', exact: true }).click()
  await expect(page.getByText('Доступ и совпадение издания уточняются у провайдера.')).toBeVisible()
  for (const offer of offers) {
    await page.context().route(offer.url, async route => {
      expect(route.request().url()).not.toContain('synthetic-miniapp-proof')
      expect(route.request().headers().authorization).toBeUndefined()
      expect(route.request().headers().cookie).toBeUndefined()
      await route.fulfill({ contentType: 'text/html', body: '<title>External provider fixture</title>' })
    })
    const link = page.getByRole('link', { name: `${offer.format === 'text' ? 'Читать' : 'Слушать'} · ${offer.provider}`, exact: true })
    await expect(link).toHaveAttribute('rel', 'noopener noreferrer')
    const opened = page.context().waitForEvent('page')
    await link.click()
    const provider = await opened
    await expect(provider).toHaveURL(offer.url)
    expect(await provider.evaluate(() => window.opener)).toBeNull()
    await provider.close()
    await page.context().unroute(offer.url)
  }
  await expect(page.getByRole('combobox', { name: 'Статус', exact: true })).toHaveAttribute('value', 'not_started')
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
    await navigateMini(page, 'Литература')
  }
  await openReading()
  const next = page.getByRole('region', { name: 'Следующий шаг чтения' })
  await next.getByRole('button', { name: /^Начать «/ }).click()
  const title = await page.locator('.literature-detail h2').innerText()
  await chooseMenu(page, page.getByRole('combobox', { name: 'Статус', exact: true }), 'in_progress')
  await page.getByRole('button', { name: 'Сохранить чтение' }).click()
  await expect(page.getByText('Отметка сохранена.')).toBeVisible()
  await openReading()
  await next.getByRole('button', { name: `Продолжить «${title}»`, exact: true }).click()
  await expect(page.getByRole('combobox', { name: 'Статус', exact: true })).toHaveAttribute('value', 'in_progress')
  await chooseMenu(page, page.getByRole('combobox', { name: 'Статус', exact: true }), 'read')
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

test('Mini App reads the authenticated legacy catalog when the old server lacks compact CORS preflight', async ({ page, request }) => {
  const backend = 'http://127.0.0.1:8085'
  expect((await request.post(backend + '/__test/reset', { data: { seed: true } })).ok()).toBe(true)
  const proof = new URLSearchParams({ auth_date: String(Math.floor(Date.now() / 1000)), user: JSON.stringify({ id: 4242, first_name: 'Synthetic learner' }) })
  const secret = createHmac('sha256', 'WebAppData').update('123:synthetic-e2e').digest()
  proof.set('hash', createHmac('sha256', secret).update([...proof.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([k, v]) => `${k}=${v}`).join('\n')).digest('hex'))
  await page.route('https://telegram.org/js/telegram-web-app.js', route => route.abort())
  await page.addInitScript(initData => { window.Telegram = { WebApp: { initData, ready() {}, expand() {} } } }, proof.toString())
  const paths: string[] = []
  await page.route('https://quiz-api.librechat.online/miniapp/**', async route => {
    const url = new URL(route.request().url())
    if (url.pathname.endsWith('/catalog-compact')) {
      // Old FastAPI has neither this GET route nor its OPTIONS handler. The
      // browser sees CORS failure, not a readable HTTP404 JSON response.
      return route.fulfill({ status: 404, contentType: 'application/json', body: '{"detail":"Not Found"}' })
    }
    if (route.request().method() === 'OPTIONS') return route.fulfill({ status: 204, headers: { 'Access-Control-Allow-Origin': site.slice(0, -1), 'Access-Control-Allow-Methods': 'GET, POST, OPTIONS', 'Access-Control-Allow-Headers': 'Authorization, Content-Type' } })
    paths.push(url.pathname)
    expect(route.request().headers().authorization).toBe('tma ' + proof.toString())
    const response = await route.fetch({ url: backend + url.pathname + url.search })
    await route.fulfill({ response, headers: { ...response.headers(), 'Access-Control-Allow-Origin': site.slice(0, -1) } })
  })
  await page.goto(site)
  await expect(page.getByRole('heading', { name: 'Что изучим сегодня?' })).toBeVisible()
  await navigateMini(page, 'Литература')
  await expect(page.locator('.literature-card').first()).toBeVisible()
  expect(paths.filter(path => path.endsWith('/literature/items'))).toHaveLength(1)
})


test('Mini App navigation marks the current section and integrates Telegram BackButton', async ({ page }, testInfo) => {
  await page.route('https://telegram.org/js/telegram-web-app.js', route => route.abort())
  await page.addInitScript(() => {
    const state = { shown: false, callback: null as (() => void) | null }
    ;(window as any).__backButton = state
    ;(window as any).Telegram = { WebApp: { initData: 'synthetic-miniapp-proof', ready() {}, expand() {}, BackButton: {
      show() { state.shown = true }, hide() { state.shown = false },
      onClick(callback: () => void) { state.callback = callback }, offClick(callback: () => void) { if (state.callback === callback) state.callback = null },
    } } }
  })
  await page.route('https://quiz-api.librechat.online/miniapp/**', async route => {
    if (route.request().method() === 'OPTIONS') { await route.fulfill({ status: 204, headers: { 'Access-Control-Allow-Origin': site.slice(0, -1), 'Access-Control-Allow-Methods': 'GET, POST, OPTIONS', 'Access-Control-Allow-Headers': 'Authorization, Content-Type' } }); return }
    const payload = route.request().url().endsWith('setup-options') ? { setup_options: setup } : { runner_state: { state: 'setup', status: 'setup', session: null } }
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ ok: true, ...payload }), headers: { 'Access-Control-Allow-Origin': site.slice(0, -1) } })
  })
  await page.goto(site)
  const quiz = page.getByRole('button', { name: 'Квиз', exact: true, includeHidden: true })
  await expect(quiz).toHaveAttribute('aria-current', 'page')
  if ((page.viewportSize()?.width ?? 1280) <= 800) {
    await expect(page.getByRole('navigation', { name: 'Разделы Mini App', includeHidden: true })).not.toBeVisible()
    await expect(page.getByRole('heading', { name: 'Что изучим сегодня?' })).toBeInViewport()
  }
  await navigateMini(page, 'Мои данные')
  await expect(page.getByRole('heading', { name: 'Мои учебные данные' })).toBeVisible()
  await expect.poll(() => page.evaluate(() => (window as any).__backButton.shown)).toBe(true)
  await page.screenshot({ path: `test-results/review-mini-navigation-${testInfo.project.name}.png` })
  await page.evaluate(() => (window as any).__backButton.callback())
  await expect(page.getByRole('heading', { name: 'Что изучим сегодня?' })).toBeVisible()
  await expect.poll(() => page.evaluate(() => (window as any).__backButton.shown)).toBe(false)
  await expect(quiz).toHaveAttribute('aria-current', 'page')
})


test('canonical new bank reaches Mini App topics and structured homework cases', async ({ page, request }, testInfo) => {
  const backend = 'http://127.0.0.1:8085'
  expect((await request.post(backend + '/__test/reset', { data: { canonical_bank: true } })).ok()).toBeTruthy()
  const proof = new URLSearchParams({ auth_date: String(Math.floor(Date.now() / 1000)), user: JSON.stringify({ id: 4242, first_name: 'Synthetic learner' }) })
  const secret = createHmac('sha256', 'WebAppData').update('123:synthetic-e2e').digest()
  proof.set('hash', createHmac('sha256', secret).update([...proof.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([k, v]) => `${k}=${v}`).join('\n')).digest('hex'))
  await page.route('https://telegram.org/js/telegram-web-app.js', route => route.abort())
  await page.addInitScript(initData => { window.Telegram = { WebApp: { initData, ready() {}, expand() {} } } }, proof.toString())
  await page.route('https://quiz-api.librechat.online/miniapp/**', async route => {
    if (route.request().method() === 'OPTIONS') return route.fulfill({ status: 204, headers: { 'Access-Control-Allow-Origin': site.slice(0, -1), 'Access-Control-Allow-Methods': 'GET, POST, OPTIONS', 'Access-Control-Allow-Headers': 'Authorization, Content-Type' } })
    const url = new URL(route.request().url())
    const response = await route.fetch({ url: backend + url.pathname + url.search })
    await route.fulfill({ response, headers: { ...response.headers(), 'Access-Control-Allow-Origin': site.slice(0, -1) } })
  })
  await page.goto(site)
  await expect(page.getByRole('heading', { name: 'Что изучим сегодня?', exact: true })).toBeVisible()
  for (const name of ['Когнитивно-поведенческая терапия', 'Супервизия психологического консультирования']) {
    await expect(page.getByRole('radio', { name, exact: true })).toBeVisible()
  }
  await navigateMini(page, 'Глоссарий')
  for (const id of ['cognitive_behavioral_therapy', 'counseling_supervision']) {
    await page.getByLabel('Тема глоссария').selectOption(id)
    await expect(page.getByRole('button', { name: 'Начать тест по терминам' })).toBeEnabled()
  }
  await navigateMini(page, 'Домашние задания')
  const card = page.locator('.homework-card').filter({ has: page.getByRole('heading', { name: 'ABC-разбор и дневник наблюдений', exact: true }) })
  await card.getByRole('button', { name: 'Начать тест · 5 вопросов', exact: true }).click()
  const choices = [0, 1, 1, 0, 3]
  for (let index = 0; index < choices.length; index++) {
    if (index === 4) {
      await expect(page.locator('.question-heading')).toContainText('Клиент записал в дневнике')
      await expect(page.locator('.question-heading')).not.toContainText(/вымышленн|выдуманн/i)
      await page.screenshot({ path: `test-results/bank-quality-miniapp-${testInfo.project.name}-homework-case.png`, fullPage: true })
    }
    await page.getByRole('radio').nth(choices[index]).check()
    await page.getByRole('button', { name: 'Проверить ответ', exact: true }).click()
    if (index === 4) await expect(page.getByRole('heading', { name: 'Разбор кейса', exact: true })).toBeVisible()
    await page.getByRole('button', { name: index === 4 ? 'Посмотреть результат' : 'Следующий вопрос', exact: true }).click()
  }
  await expect(page.getByRole('heading', { name: '80% верных ответов', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'К заданиям', exact: true }).click()
  await page.reload()
  await navigateMini(page, 'Домашние задания')
  await expect(card.locator('.homework-status')).toContainText('Выполнено · лучший результат 4 из 5')
  await navigateMini(page, 'Литература')
  const search = page.getByRole('searchbox', { name: 'Поиск по названию или автору', exact: true })
  for (const title of ['Когнитивно-поведенческая терапия. От основ к направлениям', 'История комфортного консультанта']) {
    await search.fill(title)
    await expect(page.locator('.literature-title').filter({ hasText: title })).toBeVisible()
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
})
