import { expect, type Page } from '@playwright/test'

export async function studyChoice(page: Page, label: string, value: string) {
  await page.getByRole('combobox', { name: label, exact: true }).click()
  await page.locator(`[role="option"][data-value="${value}"]`).click()
}

export async function scopeHomework(page: Page) {
  await studyChoice(page, 'Модуль обучения', 'module7')
  await studyChoice(page, 'Дисциплина', 'cognitive_behavioral_therapy')
  await studyChoice(page, 'Тема домашних заданий', 't_b7c2c2b3b5e0')
  await expect(page.locator('.homework-card')).toHaveCount(1)
  await expect(page.locator('.homework-card')).toContainText('ABC-разбор и дневник наблюдений')
}

export async function scopeLiterature(page: Page) {
  await page.getByRole('searchbox', { name: 'Поиск по названию или автору', exact: true }).fill('')
  await studyChoice(page, 'Модуль обучения', 'module7')
  await studyChoice(page, 'Дисциплина', 'cognitive_behavioral_therapy')
  await page.getByRole('combobox', { name: 'Тема курса', exact: true }).click()
  const leaf = page.locator('[role="option"][data-value]:not([data-value=""])').first()
  expect(await leaf.getAttribute('data-value')).toBeTruthy()
  await leaf.click()
  await expect(page.locator('.literature-title').first()).toBeVisible()
  await expect(page.getByRole('combobox', { name: 'Дисциплина', exact: true })).toHaveAttribute('value', 'cognitive_behavioral_therapy')
}

export async function scopedQuiz(page: Page, endpoint: string, screenshot: string) {
  await page.getByRole('button', { name: 'Выбрать следующий квиз', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Что изучим сегодня?', exact: true })).toBeVisible()
  await studyChoice(page, 'Модуль обучения', 'module7')
  const discipline = page.locator('.study-discipline').filter({ has: page.getByRole('radio', { name: 'Когнитивно-поведенческая терапия', exact: true }) })
  await discipline.locator('summary').click()
  const leaf = discipline.locator('.study-topic input').first()
  const topicId = await leaf.getAttribute('value')
  const count = Number((await leaf.locator('..').innerText()).match(/· (\d+) вопр\./)?.[1])
  expect(topicId).toMatch(/^t_[0-9a-f]{12}$/)
  expect(count).toBeGreaterThan(0)
  await leaf.check()
  await page.screenshot({ path: screenshot, fullPage: true })
  await page.getByRole('button', { name: '5', exact: true }).click()
  const response = page.waitForResponse(value => value.url().endsWith(endpoint) && value.request().method() === 'POST')
  await page.getByRole('button', { name: 'Начать квиз', exact: true }).click()
  const result = await response
  expect(result.ok()).toBeTruthy()
  const body = result.request().postDataJSON()
  expect((body.payload ?? body).topic_ids).toEqual([topicId])
  expect((await result.json()).runner_state.progress.total_questions).toBe(Math.min(5, count))
  await expect(page.getByRole('button', { name: 'Не знаю', exact: true })).toBeVisible()
}
