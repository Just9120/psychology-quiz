// Redistributed browser code: include exact installed copyright/permission text.
import { createRequire } from 'node:module'
import { dirname, join } from 'node:path'
import { readFile, writeFile } from 'node:fs/promises'

const require = createRequire(import.meta.url)
const packages = ['react', 'react-dom', 'scheduler', 'vite']
const sections = ['PsychologyAtlas — notices for redistributed browser components.\n']
for (const name of packages) {
  const resolver = name === 'scheduler' ? createRequire(require.resolve('react-dom/package.json')) : require
  const file = resolver.resolve(name + '/package.json')
  const pkg = JSON.parse(await readFile(file, 'utf8'))
  let license = await readFile(join(dirname(file), name === 'vite' ? 'LICENSE.md' : 'LICENSE'), 'utf8')
  if (name === 'vite') {
    // The browser contains Vite's generated module-preload polyfill, not Vite's
    // bundled build-time dependency graph. Preserve its complete core license.
    const boundary = '\n# Licenses of bundled dependencies'
    if (!license.includes(boundary)) throw Error('Review Vite runtime license layout')
    license = license.split(boundary)[0]
  }
  if (!license.includes('Permission is hereby granted') || !license.includes('THE SOFTWARE IS PROVIDED'))
    throw Error('Review changed browser component license: ' + name)
  sections.push(`===== ${pkg.name} ${pkg.version} =====\n\n${license.trim()}\n`)
}
const text = sections.join('\n')
await Promise.all(['../public/third-party-notices.txt', '../miniapp-app/public/third-party-notices.txt'].map(
  path => writeFile(new URL(path, import.meta.url), text)))
console.log('Browser third-party notices: ' + packages.join(', '))
