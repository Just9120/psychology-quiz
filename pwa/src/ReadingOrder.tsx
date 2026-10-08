import type { ReadingStatus } from './types'

type Item = { id: string; work_id?: string; title?: string; importance?: string | null; importance_source?: string | null; reading_level?: string | null; why_read?: string | null; prerequisites?: string[]; user_state?: { reading_status: ReadingStatus } | null }
const stages: Record<string, string> = { foundation: 'Начать с основ', core: 'Основное чтение', applied: 'Применение', deepening: 'Углубление', advanced: 'Продвинутый уровень', reference: 'Справочные материалы' }
const importance: Record<string, number> = { basic: 0, important: 1, additional: 2, advanced: 3 }
const statuses: Record<ReadingStatus, string> = { not_started: 'Не начато', in_progress: 'Читаю', read: 'Прочитано', deferred: 'Отложено' }

export function readingOrder(items: Item[], allItems: Item[] = items) {
  const known = new Map(allItems.map(item => [item.id, item]))
  const candidates = new Map<string, Item>()
  for (const item of items) {
    if (!Object.hasOwn(stages, item.reading_level ?? '') || !Object.hasOwn(importance, item.importance ?? '')
      || !['agent', 'teacher'].includes(item.importance_source ?? '') || !item.why_read?.trim()
      || !Array.isArray(item.prerequisites) || item.prerequisites.some(ref => !known.has(ref))) continue
    const key = item.work_id ?? item.id
    if (!candidates.has(key)) candidates.set(key, item)
  }
  const remaining = new Set(candidates.keys())
  const rank = (item: Item) => Object.keys(stages).indexOf(item.reading_level!)
  const dependencies = (item: Item) => item.prerequisites!.map(ref => known.get(ref)!)
  const result: { item: Item; stage: string; prerequisites: Item[] }[] = []
  while (remaining.size) {
    const ready = [...remaining].filter(key => !dependencies(candidates.get(key)!).some(item => remaining.has(item.work_id ?? item.id)))
    if (!ready.length) break
    ready.sort((a, b) => {
      const first = candidates.get(a)!, second = candidates.get(b)!
      return importance[first.importance!] - importance[second.importance!] || rank(first) - rank(second) || (first.id < second.id ? -1 : first.id > second.id ? 1 : 0)
    })
    const item = candidates.get(ready[0])!
    result.push({ item, stage: stages[item.reading_level!], prerequisites: dependencies(item) })
    remaining.delete(ready[0])
  }
  return result
}

export function ReadingOrder({ items, allItems, busy, onSelect }: { items: Item[]; allItems: Item[]; busy: boolean; onSelect: (id: string) => void }) {
  const order = readingOrder(items, allItems)
  return <details className="panel reading-order"><summary>Рекомендуемая последовательность чтения</summary>
    <p>Рекомендация агента: сначала книги, необходимые для подготовки. Для остальных учитываются значимость и этап чтения. Книги одного этапа без зависимостей можно выбирать по интересу.</p>
    {order.length ? <ol>{order.map(({ item, stage, prerequisites }) => <li key={item.work_id ?? item.id}>
      <p><button className="text-button" disabled={busy} onClick={() => onSelect(item.id)}>{item.title ?? 'Книга'}</button> · {statuses[item.user_state?.reading_status ?? 'not_started']}</p>
      <p className="muted">{stage}{item.importance_source === 'teacher' ? ' · приоритет преподавателя' : ''}. {item.why_read}</p>
      {prerequisites.length > 0 && <p>Подготовка: {prerequisites.map((required, index) => <span key={required.id}>{index > 0 && ', '}<button className="text-button" disabled={busy} onClick={() => onSelect(required.id)}>{required.title ?? 'Книга'}</button>{required.user_state?.reading_status === 'read' && ' ✓'}</span>)}</p>}
    </li>)}</ol> : <p>Для выбранной темы последовательность пока не определена.</p>}
    <p className="muted">Материалы без проверенных сведений о подготовке остаются в каталоге вне последовательности.</p>
  </details>
}
