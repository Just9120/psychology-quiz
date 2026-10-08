import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { ChoiceMenu } from '../src/ChoiceMenu'

const options = Array.from({ length: 10 }, (_, index) => ({ value: String(index), label: `Тема ${index}`, disabled: index === 8 }))

it('searches long labels, reports empty results, chooses with keys and returns focus', async () => {
  const onChange = vi.fn()
  render(<ChoiceMenu label="Тема" value="0" options={options} onChange={onChange} />)
  const user = userEvent.setup(), trigger = screen.getByRole('combobox', { name: 'Тема' })
  trigger.focus()
  await user.keyboard('{ArrowDown}')
  const search = screen.getByRole('searchbox', { name: 'Поиск: Тема' })
  expect(search).toHaveFocus()
  await user.type(search, 'несуществующая')
  expect(screen.queryAllByRole('option')).toHaveLength(0)
  expect(screen.getByRole('status')).toHaveTextContent('Ничего не найдено')
  await user.clear(search)
  await user.type(search, 'ТЕМА 9')
  expect(screen.getAllByRole('option')).toHaveLength(1)
  await user.keyboard('{Enter}')
  expect(onChange).toHaveBeenCalledExactlyOnceWith('9')
  expect(trigger).toHaveFocus()
  expect(trigger).toHaveAttribute('aria-expanded', 'false')
  await user.click(trigger)
  await user.keyboard('{Escape}')
  expect(trigger).toHaveFocus()
  expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
})

it('skips disabled choices, closes outside and blocks changes while busy', async () => {
  const onChange = vi.fn(), user = userEvent.setup()
  const props = { label: 'Статус', value: '0', options: options.slice(6), onChange }
  const view = render(<><ChoiceMenu {...props} /><button>Вне меню</button></>)
  await user.click(screen.getByRole('combobox'))
  await user.keyboard('{Home}{ArrowDown}{ArrowDown}{Enter}')
  expect(onChange).toHaveBeenCalledExactlyOnceWith('9')
  await user.click(screen.getByRole('combobox'))
  await user.click(screen.getByRole('option', { name: 'Тема 8' }))
  expect(onChange).toHaveBeenCalledTimes(1)
  await user.click(screen.getByRole('button', { name: 'Вне меню' }))
  expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
  view.rerender(<ChoiceMenu {...props} disabled />)
  expect(screen.getByRole('combobox')).toBeDisabled()
  await user.click(screen.getByRole('combobox'))
  expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
})
