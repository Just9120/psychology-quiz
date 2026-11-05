import type { Choice } from './ChoiceMenu'

export type StudyPath = { module: string; discipline_id: string; discipline: string; topic_id: string; topic: string }
export type StudyScope = { module: string; discipline: string; topic: string }
export const emptyStudyScope: StudyScope = { module: '', discipline: '', topic: '' }

export function moduleId(value?: string): string {
  if (!value) return 'unmapped'
  const match = /^(?:module|Модуль\s+)([1-9][0-9]*)$/u.exec(value)
  if (match) return `module${match[1]}`
  return ['other', 'Другое'].includes(value) ? 'other' : 'unmapped'
}

export function moduleLabel(value: string): string {
  return /^module[1-9][0-9]*$/.test(value) ? `Модуль ${value.slice(6)}` : value === 'other' ? 'Дополнительные материалы' : 'Без модуля'
}

function choices(paths: StudyPath[], key: 'module' | 'discipline_id' | 'topic_id', label: (item: StudyPath) => string): Choice[] {
  return [...new Map(paths.map(path => [path[key], { value: path[key], label: label(path) }])).values()]
    .sort((a, b) => key === 'module' ? a.value.localeCompare(b.value, 'en', { numeric: true }) : a.label.localeCompare(b.label, 'ru'))
}

export function studyChoices(paths: StudyPath[], selected: StudyScope) {
  const modules = choices(paths, 'module', path => moduleLabel(path.module))
  const module = modules.some(item => item.value === selected.module) ? selected.module : ''
  const inModule = paths.filter(path => !module || path.module === module)
  const disciplines = choices(inModule, 'discipline_id', path => path.discipline)
  const discipline = disciplines.some(item => item.value === selected.discipline) ? selected.discipline : ''
  const topics = choices(inModule.filter(path => !discipline || path.discipline_id === discipline), 'topic_id',
    path => discipline ? path.topic : `${path.topic} · ${path.discipline}`)
  const topic = topics.some(item => item.value === selected.topic) ? selected.topic : ''
  return { scope: { module, discipline, topic }, modules, disciplines, topics }
}

export function matchesStudy(paths: StudyPath[], scope: StudyScope): boolean {
  return paths.some(path => (!scope.module || path.module === scope.module)
    && (!scope.discipline || path.discipline_id === scope.discipline)
    && (!scope.topic || path.topic_id === scope.topic))
}

export type ReadingDiscipline = { topic_id: string; title: string; module?: string; modules?: string[] }
export function literaturePaths(entry: { topic_id: string; topic_title?: string; module?: string; curriculum_topics?: { id: string; title: string }[] }, disciplines: ReadingDiscipline[]): StudyPath[] {
  const discipline = disciplines.find(item => item.topic_id === entry.topic_id)
  // The entry's reviewed association is more precise than the discipline's
  // possible modules. No topic binding is invented for a general reading list.
  const modules = entry.module ? [moduleId(entry.module)] : (discipline?.modules ?? [moduleId(discipline?.module)])
  const topics = entry.curriculum_topics?.length ? entry.curriculum_topics : [{ id: `general:${entry.topic_id}`, title: 'Общее чтение дисциплины' }]
  return (modules.length ? modules : ['other']).flatMap(module => topics.map(topic => ({ module, discipline_id: entry.topic_id,
    discipline: discipline?.title ?? entry.topic_title ?? 'Другие материалы', topic_id: topic.id, topic: topic.title })))
}
