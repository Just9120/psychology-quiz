import type { LiteratureAccessLink } from './types'
import { SourcesMenu } from './SourcesMenu'

const labels = { free: 'Бесплатно', subscription: 'По подписке', purchase: 'Отдельная покупка' } as const

export function BookOffers({ links, description = 'Ссылка ведёт к провайдеру. Наличие доступа, цена и совпадение издания проверяются там.' }: { links?: LiteratureAccessLink[]; description?: string }) {
  if (!links?.length) return <div className="book-offers-empty"><h3>Читать или слушать</h3><p className="hint">Для этой книги прямые карточки сервисов пока не подтверждены. Ниже можно поискать текст и аудио в каталогах.</p></div>
  const familiar = new Set(['Литрес', 'MyBook', 'Яндекс Книги'])
  const visible = links.filter(link => familiar.has(link.provider))
  // Never hide the only available format merely because its publisher is new.
  for (const link of links) {
    if (!visible.some(item => item.format === link.format && item.narration === link.narration)) visible.push(link)
  }
  const additional = links.filter(link => !visible.includes(link))
  function offers(items: LiteratureAccessLink[]) {
    return <div className="book-offer-grid">{items.map(link => <div className="book-offer" key={link.url}>
      <span className="book-format">{link.format === 'text' ? 'Электронная книга' : link.narration === 'synthetic' ? 'Автоозвучка' : 'Аудиокнига'}</span>
      <a className="button secondary" data-format={link.format} href={link.url} target="_blank" rel="noopener noreferrer">{link.format === 'text' ? 'Читать' : 'Слушать'} · {link.provider} <span aria-hidden="true">↗</span></a>
      <span className="hint">{link.access_modes?.length ? link.access_modes.map(mode => labels[mode]).join(' · ') : 'Условия доступа уточняйте в сервисе'}</span>
    </div>)}</div>
  }
  return <section className="literature-access"><h3>Читать или слушать</h3><p className="hint">{description}</p>
    {offers(visible)}
    {additional.length > 0 && <SourcesMenu key={links.map(link => link.url).join('|')} label={`Ещё источники (${additional.length})`}>{offers(additional)}</SourcesMenu>}
    <details className="offer-details"><summary>Издание и условия доступа</summary><p className="hint">Условия могут измениться; наличие вашей подписки не предполагается. Сверьте автора, издание и формат на странице сервиса.</p>
      {links.map(link => <p className="hint" key={link.url}>{link.provider} · {link.format === 'text' ? 'Текст' : link.narration === 'synthetic' ? 'Автоозвучка' : 'Аудио'} · Проверка: {link.checked_at}</p>)}
    </details>
  </section>
}
