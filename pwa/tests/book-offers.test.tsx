import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { BookOffers } from '../src/BookOffers'
import type { LiteratureAccessLink } from '../src/types'

describe('BookOffers format-specific conditions', () => {
  it('distinguishes a virtual reader from a narrated audiobook without claiming free access', () => {
    const base = { format: 'audio' as const, provider: 'Яндекс Книги', access: 'provider_terms' as const, checked_at: '2026-10-11' }
    const links: LiteratureAccessLink[] = [
      { ...base, narration: 'synthetic', url: 'https://books.yandex.ru/audio/Ab12Cd34', access_modes: [] },
      { ...base, url: 'https://books.yandex.ru/audiobooks/Ef56Gh78', access_modes: ['subscription'] },
    ]
    const view = render(<BookOffers links={links} />)
    expect(screen.getByText('Автоозвучка')).toBeVisible()
    expect(screen.getByText('Аудиокнига')).toBeVisible()
    expect(screen.getByText('Условия доступа уточняйте в сервисе')).toBeVisible()
    expect(screen.queryByText('Бесплатно')).not.toBeInTheDocument()
    const outgoing = screen.getAllByRole('link', { name: 'Слушать · Яндекс Книги' })
    expect(outgoing.map(link => link.getAttribute('href'))).toEqual(links.map(link => link.url))
    expect(outgoing.every(link => link.getAttribute('rel') === 'noopener noreferrer')).toBe(true)
    view.rerender(<BookOffers links={[links[1]]} />)
    expect(screen.queryByText('Автоозвучка')).not.toBeInTheDocument()
  })
  it('keeps audio unknown while text offers purchase and subscription, without assuming entitlement', () => {
    const base = { provider: 'Литрес', access: 'provider_terms' as const, checked_at: '2026-10-03' }
    const links: LiteratureAccessLink[] = [
      { ...base, format: 'text', url: 'https://www.litres.ru/book/exact/', access_modes: ['purchase', 'subscription'] },
      { ...base, format: 'audio', url: 'https://www.litres.ru/audiobook/exact/' },
    ]
    const view = render(<BookOffers links={links} />)
    expect(screen.getByText('Отдельная покупка · По подписке')).toBeVisible()
    expect(screen.getByText('Условия доступа уточняйте в сервисе')).toBeVisible()
    expect(screen.getByRole('link', { name: 'Читать · Литрес' })).toHaveAttribute('href', links[0].url)
    expect(screen.getByRole('link', { name: 'Слушать · Литрес' })).toHaveAttribute('href', links[1].url)
    expect(screen.queryByText('Бесплатно')).not.toBeInTheDocument()
    expect(screen.getAllByText(/наличие вашей подписки не предполагается/)).toHaveLength(1)
    view.rerender(<BookOffers links={[{ ...links[0], access_modes: ['free'] }]} />)
    expect(screen.getByText('Бесплатно')).toBeVisible()
    view.rerender(<BookOffers links={[]} />)
    expect(screen.getByText('Для этой книги прямые карточки сервисов пока не подтверждены. Ниже можно поискать текст и аудио в каталогах.')).toBeVisible()
  })
})
