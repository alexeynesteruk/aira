import { expect, test } from '@playwright/test'

test('built UI explains readiness while the actual API remains live', async ({ page, request }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Every requirement.Connected to its evidence.')
  await expect(page.getByRole('status')).toHaveText('Assessment processing is not available in this build.')
  await expect(page.getByText('No documents have been processed.')).toBeVisible()
  const liveness = await request.get('/health/live')
  expect(liveness.ok()).toBeTruthy()
  expect(await liveness.json()).toEqual({ status: 'ok', service: 'aira' })
  expect((await request.get('/health/ready')).status()).toBe(503)
})

test('a broken server connection remains visible to the reviewer', async ({ page }) => {
  await page.route('**/health/ready', (route) => route.abort('failed'))
  await page.goto('/')
  await expect(page.getByRole('status')).toContainText('Check the server connection and refresh.')
})
