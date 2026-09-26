import type { ReadingStatus } from './types'

export type ReadingPlanEntry = {
  id: string
  topic_id: string
  topic_order?: number | null
  priority?: string | null
  user_state?: { reading_status: ReadingStatus } | null
}

// Personal suggestion, never presented as a teacher's priority. Preserve the
// source list's order within each stage; a completed association goes last.
export function suggestedReadingOrder<T extends ReadingPlanEntry>(entries: T[]): T[] {
  return [...entries].sort((left, right) => {
    const leftDone = left.user_state?.reading_status === 'read' ? 1 : 0
    const rightDone = right.user_state?.reading_status === 'read' ? 1 : 0
    return leftDone - rightDone || left.topic_id.localeCompare(right.topic_id) ||
      (left.topic_order ?? Number.MAX_SAFE_INTEGER) - (right.topic_order ?? Number.MAX_SAFE_INTEGER) ||
      left.id.localeCompare(right.id)
  })
}

export function readingChecklistLabel(entry: ReadingPlanEntry): string {
  return entry.user_state?.reading_status === 'read' ? 'Прочитано' : 'Не завершено'
}
