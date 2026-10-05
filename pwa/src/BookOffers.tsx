import type { LiteratureAccessLink } from './types'

const labels = { free: 'Бесплатно', subscription: 'По подписке', purchase: 'Отдельная покупка' } as const

export function BookOffers({ links, description = 'Ссылка ведёт к провайдеру. Наличие доступа, цена и совпадение издания проверяются там.' }: { links?: LiteratureAccessLink[]; description?: string }) {
  if (!links?.length) return <p className="muted">Проверенных ссылок на текст или аудио пока нет.</p>
  return <div className="literature-access"><h3>Внешние версии</h3>
    <p className="muted">{description}</p>
    {links.map(link => <div key={link.url}>
      <p><a href={link.url} target="_blank" rel="noopener noreferrer">{link.format === 'text' ? 'Текст' : 'Аудио'} · {link.provider}</a></p>
      <p>{link.access_modes?.length ? link.access_modes.map(mode => labels[mode]).join(' · ') : 'Условия доступа не подтверждены'}</p>
      <p className="muted">Проверка: {link.checked_at}. Условия сервиса могут измениться; наличие вашей подписки не предполагается.</p>
    </div>)}
  </div>
}
