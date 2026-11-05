import { render, screen } from '@testing-library/react'
import { expect, it } from 'vitest'
import { QuestionPrompt } from '../src/QuestionPrompt'

it('preserves all conditions in readable body text with a short accessible heading', () => {
  const text = 'Клиент сообщает о трудностях на работе. Встреча первая, запрос пока не уточнён.\nКакие сведения нужно уточнить перед выбором следующего шага?'
  render(<QuestionPrompt text={text} number={3} />)
  expect(screen.getByRole('heading', { level: 1, name: 'Вопрос 3' })).toBeVisible()
  expect(document.querySelector('.question-body')?.textContent).toBe(text)
  expect(screen.queryByRole('heading', { name: text })).not.toBeInTheDocument()
})

it('keeps a short question as the heading', () => {
  render(<QuestionPrompt text="Что означает внутренняя валидность?" number={2} />)
  expect(screen.getByRole('heading', { name: 'Что означает внутренняя валидность?' })).toBeVisible()
  expect(document.querySelector('.question-body')).toBeNull()
})
