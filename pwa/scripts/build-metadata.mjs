import { createHash } from 'node:crypto'
import { execFileSync } from 'node:child_process'
import { readdir, readFile, writeFile } from 'node:fs/promises'
import { join, relative } from 'node:path'

const revision = process.env.PWA_BUILD_SHA || execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim()
if (!/^[a-f0-9]{40}$/.test(revision)) throw new Error('PWA_BUILD_SHA must be a full commit SHA')
const dirty = !process.env.PWA_BUILD_SHA && Boolean(execFileSync('git', ['status', '--porcelain', '--', '.'], { encoding: 'utf8' }).trim())
const version = revision + (dirty ? '-dirty' : '')
const worker = await readFile('dist/sw.js', 'utf8')
await writeFile('dist/sw.js', worker.replace('__BUILD_VERSION__', version))
async function files(directory) {
  const entries = await readdir(directory, { withFileTypes: true })
  return (await Promise.all(entries.map(entry => entry.isDirectory() ? files(join(directory, entry.name)) : [join(directory, entry.name)]))).flat()
}
const hashes = {}
for (const path of (await files('dist')).sort()) {
  hashes[relative('dist', path).replaceAll('\\', '/')] = createHash('sha256').update(await readFile(path)).digest('hex')
}
await writeFile('dist/build.json', JSON.stringify({ revision, dirty, files: hashes }, null, 2) + '\n')
console.log(`PWA build ${version}: ${Object.keys(hashes).length} assets`)
