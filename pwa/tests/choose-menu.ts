import { screen } from '@testing-library/react'
import type userEvent from '@testing-library/user-event'

export async function chooseMenu(user: ReturnType<typeof userEvent.setup>, field: HTMLElement, value: string) {
  await user.click(field)
  const option = screen.getAllByRole('option').find(item => item.getAttribute('data-value') === value)
  if (!option) throw new Error(`Missing menu choice: ${value}`)
  await user.click(option)
}
