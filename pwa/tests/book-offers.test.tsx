import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { BookOffers } from '../src/BookOffers'
import type { LiteratureAccessLink } from '../src/types'

describe('BookOffers format-specific conditions', () => {
  it('keeps audio unknown while text offers purchase and subscription, without assuming entitlement', () => {
    const base = { provider: 'Литрес', access: 'provider_terms' as const, checked_at: '2026-10-03' }
    const links: LiteratureAccessLink[] = [
      { ...base, format: 'text', url: 'https://www.litres.ru/book/exact/', access_modes: ['purchase', 'subscription'] },
      { ...base, format: 'audio', url: 'https://www.litres.ru/audiobook/exact/' },
    ]
    const view = render(<BookOffers links={links} />)
    expect(screen.getByText('Отдельная покупка · По подписке')).toBeVisible()
    expect(screen.getByText('Условия доступа не подтверждены')).toBeVisible()
    expect(screen.queryByText('Бесплатно')).not.toBeInTheDocument()
    expect(screen.getAllByText(/наличие вашей подписки не предполагается/)).toHaveLength(2)
    view.rerender(<BookOffers links={[{ ...links[0], access_modes: ['free'] }]} />)
    expect(screen.getByText('Бесплатно')).toBeVisible()
    view.rerender(<BookOffers links={[]} />)
    expect(screen.getByText('Проверенных ссылок на текст или аудио пока нет.')).toBeVisible()
  })
})
