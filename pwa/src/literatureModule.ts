export function literatureModuleLabel(module: string): string {
  return module === 'other' ? 'Другое' : module.replace('module', 'Модуль ')
}
