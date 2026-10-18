import { expect, test } from '@playwright/test'

test('built UI reports readiness exactly as the API does', async ({ page, request }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Every requirement.Connected to its evidence.')
  const liveness = await request.get('/health/live')
  expect(liveness.ok()).toBeTruthy()
  expect(await liveness.json()).toEqual({ status: 'alive' })
  const readiness = await request.get('/health/ready')
  const body = await readiness.json()
  if (readiness.status() === 503) {
    expect(body.ready).toBe(false)
    expect(body.provider.status).toBe('unverified')
    expect(body.missing_prerequisites.length).toBeGreaterThan(0)
    await expect(page.getByRole('status')).toHaveText('Assessment processing is not available.')
    await expect(page.getByText(body.missing_prerequisites[0])).toBeVisible()
  } else {
    expect(readiness.status()).toBe(200)
    expect(body.ready).toBe(true)
    await expect(page.getByRole('status')).toHaveText('Ready to assess documents.')
  }
})

test('a broken server connection remains visible to the reviewer', async ({ page }) => {
  await page.route('**/health/ready', (route) => route.abort('failed'))
  await page.goto('/')
  await expect(page.getByRole('status')).toContainText('Check the server connection and refresh.')
})
