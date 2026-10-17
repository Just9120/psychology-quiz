import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { BookSearch } from '../src/BookSearch'

describe('BookSearch shared by PWA and Mini App', () => {
  it('separates additional catalogue searches from confirmed book offers and safely encodes the query', async () => {
    const user = userEvent.setup()
    const query = '"Смысл & язык" И. Автор скачать'
    const view = render(<BookSearch search={{ query, url: 'https://www.google.com/search?q=test' }} />)
    expect(screen.queryByRole('link', { name: 'МИФ ↗' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Поиск в других каталогах' }))
    for (const name of ['МИФ ↗', 'Альпина ↗', 'Питер ↗']) {
      const link = screen.getByRole('link', { name })
      const url = new URL(link.getAttribute('href')!)
      expect(url.searchParams.get(name === 'МИФ ↗' ? 'query' : 'q')).toBe('"Смысл & язык" И. Автор')
      expect(link).toHaveAttribute('rel', 'noopener noreferrer')
      expect(link).toHaveAttribute('target', '_blank')
    }
    expect(screen.getByText(/В каталоге могут быть бумажные книги/)).toBeVisible()
    view.rerender(<BookSearch search={{ query: 'Другая', url: 'https://www.google.com/' }} />)
    expect(screen.getByRole('button', { name: 'Поиск в других каталогах' })).toHaveAttribute('aria-expanded', 'false')
  })
  it('shows a selectable exact query and outbound search without treating it as a book offer', () => {
    const query = '"Смысл & язык" И. Автор скачать'
    render(<BookSearch search={{ query, url: 'https://www.google.com/search?q=test' }} />)
    expect(screen.getByRole('textbox', { name: 'Поисковый запрос книги' })).toHaveValue(query)
    expect(screen.getByRole('textbox')).toHaveAttribute('readonly')
    expect(screen.getByRole('link', { name: 'Поиск в интернете ↗' })).toHaveAttribute('rel', 'noopener noreferrer')
    for (const name of ['Литрес ↗', 'MyBook ↗', 'Яндекс Книги ↗']) {
      const link = screen.getByRole('link', { name })
      expect(link).toHaveAttribute('target', '_blank')
      expect(link).toHaveAttribute('rel', 'noopener noreferrer')
      const url = new URL(link.getAttribute('href')!)
      expect(name.startsWith('Яндекс') ? decodeURIComponent(url.pathname.replace('/search/all/', '')) : url.searchParams.get('q')).toBe('"Смысл & язык" И. Автор')
    }
    expect(screen.getByText('Результаты поиска не подтверждают доступность скачивания.')).toBeInTheDocument()
  })
  it('copies the exact query only after success and selects it when clipboard permission fails', async () => {
    const user = userEvent.setup()
    const write = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValueOnce().mockRejectedValueOnce(new Error('Denied'))
    const view = render(<BookSearch search={{ query: 'Первая книга скачать', url: 'https://www.google.com/search?q=first' }} />)
    await user.click(screen.getByRole('button', { name: 'Скопировать запрос' }))
    expect(write).toHaveBeenCalledExactlyOnceWith('Первая книга скачать')
    expect(screen.getByRole('status')).toHaveTextContent('Поисковый запрос скопирован.')
    view.rerender(<BookSearch search={{ query: 'Другая книга скачать', url: 'https://www.google.com/search?q=second' }} />)
    await user.click(screen.getByRole('button', { name: 'Скопировать запрос' }))
    expect(screen.getByRole('status')).toHaveTextContent('Запрос выделен')
    const field = screen.getByRole('textbox') as HTMLTextAreaElement
    expect(field).toHaveFocus()
    expect(field.selectionEnd - field.selectionStart).toBe(field.value.length)
    expect(screen.queryByText('Поисковый запрос скопирован.')).not.toBeInTheDocument()
  })
  it('does not report copying a previous book as success for a new book', async () => {
    const user = userEvent.setup()
    let finish!: () => void
    vi.spyOn(navigator.clipboard, 'writeText').mockImplementation(() => new Promise<void>(resolve => { finish = resolve }))
    const view = render(<BookSearch search={{ query: 'Первая', url: 'https://www.google.com/' }} />)
    await user.click(screen.getByRole('button', { name: 'Скопировать запрос' }))
    view.rerender(<BookSearch search={{ query: 'Вторая', url: 'https://www.google.com/' }} />)
    finish()
    await vi.waitFor(() => expect(screen.getByRole('button', { name: 'Скопировать запрос' })).toBeEnabled())
    expect(screen.getByRole('status')).not.toHaveTextContent('скопирован')
  })
})
