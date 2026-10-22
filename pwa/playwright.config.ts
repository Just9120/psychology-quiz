import { defineConfig, devices } from '@playwright/test'
import { randomUUID } from 'node:crypto'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const runId = randomUUID()
const receipt = join(tmpdir(), `psychology-pwa-${runId}.json`)

export default defineConfig({
  metadata: { e2eRunId: runId, e2eReceipt: receipt },
  globalTeardown: './tests/teardown.ts',
  testDir: './tests/e2e',
  fullyParallel: false,
  workers: 1, // One disposable database; every test resets it.
  retries: 0,
  timeout: 30000,
  reporter: 'list',
  use: { baseURL: 'http://127.0.0.1:4173', trace: 'retain-on-failure' },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'] } },
    { name: 'mobile', use: { ...devices['Pixel 7'] } },
  ],
  webServer: [
    { command: `"${process.env.PWA_TEST_PYTHON || 'python'}" tests/backend.py`, url: 'http://127.0.0.1:8085/__test/health', reuseExistingServer: false, timeout: 30000,
      env: { PWA_E2E_RECEIPT: receipt, PWA_E2E_RUN_ID: runId } },
    { command: 'npm run preview', url: 'http://127.0.0.1:4173', reuseExistingServer: false, timeout: 30000 },
    { command: 'npm run preview:miniapp', url: 'http://127.0.0.1:4174', reuseExistingServer: false, timeout: 30000 },
  ],
})
