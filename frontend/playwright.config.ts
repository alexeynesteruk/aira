import { defineConfig, devices } from '@playwright/test'

const servers = [
  {
    command: 'uv run --project ../backend uvicorn app.main:app --host 127.0.0.1 --port 8000',
    url: 'http://127.0.0.1:8000/health/live',
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
  {
    command: 'uv run --project ../backend python ../tests/e2e/fixture_server.py --port 8001 --frontend-dir dist',
    url: 'http://127.0.0.1:8001/health/live',
    reuseExistingServer: false,
    timeout: 60_000,
  },
]

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: { trace: 'retain-on-failure' },
  projects: [
    {
      name: 'shell',
      testMatch: 'workspace.spec.ts',
      use: { ...devices['Desktop Chrome'], baseURL: 'http://127.0.0.1:8000' },
    },
    {
      name: 'journeys',
      testMatch: 'journeys.spec.ts',
      use: { ...devices['Desktop Chrome'], baseURL: 'http://127.0.0.1:8001' },
    },
  ],
  webServer: servers,
})
