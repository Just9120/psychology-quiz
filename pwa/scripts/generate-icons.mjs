import { Resvg } from '@resvg/resvg-js'
import { mkdir, readFile, writeFile } from 'node:fs/promises'

const svg = await readFile(new URL('../public/icon.svg', import.meta.url), 'utf8')
const directory = new URL('../public/icons/', import.meta.url)
await mkdir(directory, { recursive: true })
for (const [name, width] of [['icon-192', 192], ['icon-512', 512], ['maskable-512', 512], ['apple-touch-icon', 180]]) {
  // The book stays within the maskable safe circle; fill all corners for masking.
  const source = name.startsWith('maskable') ? svg.replace('rx="112"', 'rx="0"') : svg
  await writeFile(new URL(`${name}.png`, directory), new Resvg(source, { fitTo: { mode: 'width', value: width } }).render().asPng())
}
