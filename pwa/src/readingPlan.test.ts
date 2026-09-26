import { describe, expect, it } from 'vitest'
import { readingChecklistLabel, suggestedReadingOrder } from './readingPlan'

describe('personal reading plan', () => {
  it('moves completed associations after unfinished entries without overwriting source order or priority', () => {
    const entries = [
      { id: 'read', topic_id: 'topic', topic_order: 10, priority: 'important', user_state: { reading_status: 'read' as const } },
      { id: 'later', topic_id: 'topic', topic_order: 30, priority: null, user_state: null },
      { id: 'first', topic_id: 'topic', topic_order: 20, priority: null, user_state: { reading_status: 'in_progress' as const } },
    ]
    const ordered = suggestedReadingOrder(entries)
    expect(ordered.map(item => item.id)).toEqual(['first', 'later', 'read'])
    expect(readingChecklistLabel(ordered[0])).toBe('Не завершено')
    expect(readingChecklistLabel(ordered[2])).toBe('Прочитано')
    expect(entries[0].priority).toBe('important')
    expect(entries[0].id).toBe('read')
  })
})
