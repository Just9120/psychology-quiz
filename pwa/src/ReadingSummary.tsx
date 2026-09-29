import type { ReadingStatus } from './types'

type Item = { id: string; work_id?: string; title?: string; user_state?: { reading_status: ReadingStatus } | null }

export function ReadingSummary({ items, busy, onSelect }: { items: Item[]; busy: boolean; onSelect: (id: string) => void }) {
  const works = new Map<string, Item[]>()
  for (const item of items) {
    const key = item.work_id ?? item.id
    works.set(key, [...(works.get(key) ?? []), item])
  }
  const groups = [...works.values()]
  const statuses = (entries: Item[]) => new Set(entries.map(item => item.user_state?.reading_status ?? 'not_started'))
  const read = groups.filter(entries => statuses(entries).size === 1 && statuses(entries).has('read')).length
  const conflicts = groups.filter(entries => statuses(entries).size > 1).length
  const current = groups.map(entries => entries.find(item => item.user_state?.reading_status === 'in_progress')).filter((item): item is Item => !!item)
  return <aside className="panel reading-summary" aria-label="Прогресс списка чтения">
    <p role="status">Прочитано {read} из {groups.length}</p>
    {conflicts > 0 && <p className="muted">У {conflicts} работ отметки в выбранных списках различаются. Они не включены в число прочитанных до согласования отметок.</p>}
    <h2>Сейчас читаю</h2>
    {current.length ? <ul>{current.map(item => <li key={item.id}><button className="text-button" disabled={busy} onClick={() => onSelect(item.id)}>{item.title ?? 'Книга'}</button></li>)}</ul> : <p className="muted">В выбранных списках нет книг со статусом «Читаю».</p>}
  </aside>
}
