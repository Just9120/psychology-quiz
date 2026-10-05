import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { BookSearch } from '../src/BookSearch'

describe('BookSearch shared by PWA and Mini App', () => {
  it('shows a selectable exact query and outbound search without treating it as a book offer', () => {
    const query = '"Смысл & язык" И. Автор скачать'
    render(<BookSearch search={{ query, url: 'https://www.google.com/search?q=test' }} />)
    expect(screen.getByRole('textbox', { name: 'Поисковый запрос книги' })).toHaveValue(query)
    expect(screen.getByRole('textbox')).toHaveAttribute('readonly')
    expect(screen.getByRole('link', { name: 'Найти книгу для скачивания' })).toHaveAttribute('rel', 'noopener noreferrer')
    expect(screen.getByText('Результаты поиска не подтверждают доступность скачивания.')).toBeInTheDocument()
  })
})
