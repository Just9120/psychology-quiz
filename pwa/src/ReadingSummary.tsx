import type { ReadingStatus } from './types'

type Item = { id: string; type?: string; work_id?: string; title?: string; importance?: string | null; importance_source?: string | null; reading_level?: string | null; why_read?: string | null; prerequisites?: string[]; user_state?: { reading_status: ReadingStatus; updated_at?: string } | null }

export function readingNextStep(items: Item[], allItems: Item[] = items): Item | null {
  const known = new Map(allItems.map(item => [item.id, item]))
  const allWorks = new Map<string, Item[]>()
  for (const item of allItems) {
    const key = item.work_id ?? item.id
    allWorks.set(key, [...(allWorks.get(key) ?? []), item])
  }
  const status = (item: Item) => item.user_state?.reading_status ?? 'not_started'
  // Keep the selected association, but check the entire work for conflicts.
  const candidates = items.filter(item => {
    const group = allWorks.get(item.work_id ?? item.id) ?? []
    return group.length > 0 && group.every(entry => status(entry) === 'in_progress')
  })
  const recency = (item: Item) => {
    const value = item.user_state?.updated_at ?? ''
    if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(value)) return ''
    const time = Date.parse(value)
    return Number.isFinite(time) && new Date(time).toISOString().replace('.000Z', 'Z') === value ? value : ''
  }
  const compare = (a: string, b: string) => a < b ? -1 : a > b ? 1 : 0
  candidates.sort((a, b) => compare(recency(b), recency(a)) || compare(a.id, b.id))
  if (candidates.length) return candidates[0]
  const rank: Record<string, number> = { basic: 0, important: 1, additional: 2, advanced: 3 }
  const stages: Record<string, number> = { foundation: 0, core: 1, applied: 2, deepening: 3, advanced: 4, reference: 5 }
  const recommendations = items.filter(item => {
    const group = allWorks.get(item.work_id ?? item.id) ?? []
    return group.length > 0 && group.every(entry => status(entry) === 'not_started') &&
      Object.hasOwn(rank, item.importance ?? '') && ['agent', 'teacher'].includes(item.importance_source ?? '') &&
      Object.hasOwn(stages, item.reading_level ?? '') &&
      !!item.why_read?.trim() && Array.isArray(item.prerequisites) && item.prerequisites.every(reference => {
        const prerequisite = known.get(reference)
        return !!prerequisite && (allWorks.get(prerequisite.work_id ?? prerequisite.id) ?? []).every(entry => status(entry) === 'read')
      })
  })
  recommendations.sort((a, b) => rank[a.importance!] - rank[b.importance!] || stages[a.reading_level!] - stages[b.reading_level!] || compare(a.id, b.id))
  return recommendations[0] ?? null
}

export function readingContinuationReason(item: Item): string {
  if (item.type === 'video') return 'Вы уже начали этот видеоматериал. Продолжите просмотр перед выбором следующего.'
  if (['article', 'chapter', 'other'].includes(item.type ?? '')) return 'Вы уже начали этот материал. Продолжите работу с ним перед выбором следующего.'
  return 'Вы уже начали эту книгу. Продолжите чтение перед выбором следующей.'
}

export function ReadingSummary({ items, allItems = items, busy, onSelect, showActions = true }: { items: Item[]; allItems?: Item[]; busy: boolean; onSelect: (id: string) => void; showActions?: boolean }) {
  const works = new Map<string, Item[]>()
  for (const item of items) {
    const key = item.work_id ?? item.id
    works.set(key, [...(works.get(key) ?? []), item])
  }
  const groups = [...works.values()]
  const allWorks = new Map<string, Item[]>()
  for (const item of allItems) {
    const key = item.work_id ?? item.id
    allWorks.set(key, [...(allWorks.get(key) ?? []), item])
  }
  const statuses = (entries: Item[]) => {
    const key = entries[0].work_id ?? entries[0].id
    return new Set((allWorks.get(key) ?? entries).map(item => item.user_state?.reading_status ?? 'not_started'))
  }
  const read = groups.filter(entries => statuses(entries).size === 1 && statuses(entries).has('read')).length
  const conflicts = groups.filter(entries => statuses(entries).size > 1).length
  const current = groups.map(entries => entries.find(item => item.user_state?.reading_status === 'in_progress')).filter((item): item is Item => !!item)
  const next = showActions ? readingNextStep(items, allItems) : null
  const continuing = next?.user_state?.reading_status === 'in_progress'
  return <aside className="panel reading-summary" aria-label="Прогресс списка чтения">
    <p role="status">Прочитано {read} из {groups.length}</p>
    {conflicts > 0 && <p className="muted">У {conflicts} работ отметки в учебных списках различаются. Они не включены в число прочитанных до согласования отметок.</p>}
    <h2>Сейчас читаю</h2>
    {current.length ? <ul>{current.map(item => <li key={item.id}>{showActions ? <button className="text-button" disabled={busy} onClick={() => onSelect(item.id)}>{item.title ?? 'Книга'}</button> : <span>{item.title ?? 'Книга'}</span>}</li>)}</ul> : <p className="muted">В выбранной теме нет книг со статусом «Читаю».</p>}
    {next && <section aria-label="Следующий шаг чтения">
      <h2>Следующий шаг</h2>
      <button className="text-button" disabled={busy} onClick={() => onSelect(next.id)}>{continuing ? 'Продолжить' : 'Начать'} «{next.title ?? 'Книга'}»</button>
      <p className="muted">{continuing ? readingContinuationReason(next) : `Рекомендация агента. ${next.why_read}${next.importance_source === 'teacher' ? (['video', 'article', 'chapter', 'other'].includes(next.type ?? '') ? ' Приоритет материала — из учебного списка.' : ' Приоритет книги — из учебного списка.') : ''}`}</p>
    </section>}
  </aside>
}
