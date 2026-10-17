import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: { baseURL: 'http://127.0.0.1:8000', trace: 'retain-on-failure' },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: process.env.AIRA_E2E_EXTERNAL_SERVER ? undefined : {
    command: 'uv run --project ../backend uvicorn app.main:app --host 127.0.0.1 --port 8000',
    url: 'http://127.0.0.1:8000/health/live',
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
})
