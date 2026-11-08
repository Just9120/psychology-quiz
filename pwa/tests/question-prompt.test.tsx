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

it.each([' ', '\n\n'])('separates the case situation while preserving the captured text (%j)', separator => {
  const situation = 'На первой встрече клиент сообщает, что после разговора с руководителем ему трудно сосредоточиться. Пока известно только его описание разговора.'
  const prompt = 'Что консультанту полезнее уточнить сначала?'
  const text = situation + separator + prompt
  const { container } = render(<QuestionPrompt text={text} number={5} />)
  expect(screen.getByRole('heading', { level: 1, name: prompt })).toBeVisible()
  expect(container.querySelector('.case-situation')?.textContent).toBe(situation + separator)
  expect(container.querySelector('.question-prompt')?.textContent).toBe(text)
})
