import type { FullConfig } from '@playwright/test'
import { lstat, readFile, readdir, rmdir, unlink } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { basename, dirname, join, resolve } from 'node:path'
import { setTimeout as delay } from 'node:timers/promises'

const absent = (failure: unknown) => (failure as NodeJS.ErrnoException).code === 'ENOENT'

export default async function teardown(config: FullConfig) {
  const runId = config.metadata.e2eRunId as string, receipt = config.metadata.e2eReceipt as string
  if (dirname(resolve(receipt)) !== resolve(tmpdir()) || basename(receipt) !== `psychology-pwa-${runId}.json`)
    throw Error('Foreign E2E receipt; preserve fixtures')
  let owner: { run_id: string; pid: number; directory: string }
  try {
    const info = await lstat(receipt)
    if (!info.isFile() || info.isSymbolicLink() || info.size > 2048) throw Error('Invalid E2E receipt')
    owner = JSON.parse(await readFile(receipt, 'utf8'))
  } catch (failure) { if (absent(failure)) return; throw failure }
  const directory = resolve(owner.directory)
  if (owner.run_id !== runId || !Number.isSafeInteger(owner.pid) || owner.pid <= 0
    || dirname(directory) !== resolve(tmpdir()) || !/^pwa-e2e-[\w-]+$/.test(basename(directory)))
    throw Error('Foreign E2E fixture; preserve it')
  // The endpoint exists only in the loopback synthetic server and checks this run's nonce.
  await fetch('http://127.0.0.1:8085/__test/shutdown', {
    method: 'POST', headers: { 'X-PWA-Test-Run': runId }, signal: AbortSignal.timeout(2000),
  }).catch(() => undefined)
  for (let attempt = 0; attempt < 100; attempt++) {
    try { process.kill(owner.pid, 0) } catch (failure) {
      if ((failure as NodeJS.ErrnoException).code === 'ESRCH') break
      throw failure
    }
    if (attempt === 99) throw Error('Synthetic backend did not stop; preserve fixtures for inspection')
    await delay(100)
  }
  try {
    const info = await lstat(directory)
    if (!info.isDirectory() || info.isSymbolicLink()) throw Error('Foreign fixture path')
    const marker = JSON.parse(await readFile(join(directory, 'owner.json'), 'utf8'))
    if (JSON.stringify(marker) !== JSON.stringify(owner)) throw Error('Foreign fixture marker')
    const files = await readdir(directory)
    if (files.some(name => !['owner.json', 'synthetic.sqlite3', 'synthetic.sqlite3-wal', 'synthetic.sqlite3-shm', 'synthetic.sqlite3-journal'].includes(name)))
      throw Error('Unexpected fixture files; preserve them')
    // Only the exact directory named by this run's receipt; never scan or delete older runs.
    for (const name of files) await unlink(join(directory, name))
    await rmdir(directory)
  } catch (failure) { if (!absent(failure)) throw failure }
  await unlink(receipt).catch(failure => { if (!absent(failure)) throw failure })
}
