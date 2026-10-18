import { expect, type Page, test } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import path from 'node:path'

/**
 * Saved staff journeys against the fixture server (port 8001). The interpreter
 * is a controlled fixture returning source-valid records; outcomes are
 * deterministic, never live-model evidence.
 */

const ROOT = path.resolve(import.meta.dirname, '../..')
const POLICY = path.join(ROOT, 'examples/guidelines/bcbs_fl_02-33000-31_2025-08-15.pdf')
const POLICY_2026 = path.join(ROOT, 'examples/guidelines/bcbs_fl_02-33000-31_2026-01-01.pdf')
const CHART = path.join(ROOT, 'examples/charts/robert_mitchell_chart_final.pdf')
const IMAGE_ONLY = path.join(ROOT, 'tests/fixtures/pdf/image-only.pdf')
const ENCRYPTED = path.join(ROOT, 'tests/fixtures/pdf/encrypted.pdf')

const FIXTURE_NOTE = 'Fixture interpreter for browser tests; no live model calls.'

async function uploadBoth(page: Page) {
  await page.goto('/')
  await expect(page.getByText(FIXTURE_NOTE)).toBeVisible()
  await page.getByLabel('Policy PDF').setInputFiles(POLICY)
  await expect(page.getByText(/bcbs_fl_02-33000-31.*pages/)).toBeVisible()
  await page.getByLabel('Chart PDF').setInputFiles(CHART)
  await expect(page.getByText(/robert_mitchell_chart_final.*pages/)).toBeVisible()
}

async function submitAndWait(page: Page) {
  await page.getByRole('button', { name: 'Start assessment' }).click()
  await expect(page).toHaveURL(/\?run=run-/)
  const runId = new URL(page.url()).searchParams.get('run')!
  return runId
}

test('mismatch journey cites both documents and shows no checklist', async ({ page }) => {
  await uploadBoth(page)
  await submitAndWait(page)
  await expect(page.getByRole('heading', { name: 'Policy does not apply to this request' })).toBeVisible({ timeout: 20_000 })
  await expect(page.getByText('Documentation readiness only — not an insurer decision.')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Requirements checklist' })).not.toBeVisible()
  await page.getByRole('button', { name: /Source, page 1/ }).first().click()
  const viewer = page.getByRole('complementary', { name: 'Source viewer' })
  await expect(viewer).toBeVisible()
  await expect(viewer.getByRole('heading', { name: /Page 1/ })).toBeVisible()
  await expect(viewer.locator('mark').first()).toHaveText('Subject: Treatments for Varicose Veins/Venous')
  await expect(viewer.getByRole('link', { name: /Open original PDF at page 1/ })).toHaveAttribute('href', /#page=1$/)
})

test('gaps journey shows the checklist, evidence states, and exports', async ({ page }) => {
  await uploadBoth(page)
  await page.getByLabel('Procedure', { exact: true }).fill('E2E gaps')
  const runId = await submitAndWait(page)
  await expect(page.getByRole('heading', { name: 'Documentation gaps or contrary evidence' })).toBeVisible({ timeout: 20_000 })
  await expect(page.getByRole('heading', { name: 'All of the following' })).toBeVisible()

  const metCard = page.getByLabel('Finding: criterion-telangiectasia')
  await expect(metCard).toBeVisible()
  await expect(metCard.locator('.badge')).toHaveText('Met')
  await expect(metCard.getByRole('button', { name: /Chart, page 3/ })).toBeVisible()

  const missingCard = page.getByLabel('Finding: criterion-perforator-reflux')
  await expect(missingCard.locator('.badge')).toHaveText('Missing')
  await expect(missingCard.getByText('Documentation needed')).toBeVisible()
  await expect(missingCard.getByRole('button', { name: /Chart/ })).not.toBeVisible()

  await metCard.getByRole('button', { name: /Policy, page 3/ }).click()
  const viewer = page.getByRole('complementary', { name: 'Source viewer' })
  await expect(viewer.getByRole('heading', { name: /Page 3/ })).toBeVisible()
  await expect(viewer.locator('mark').first()).toHaveText('Treatment of telangiectasia such as spider veins')
  await metCard.getByRole('button', { name: /Chart, page 3/ }).click()
  await expect(viewer.getByRole('heading', { name: /Page 3/ })).toBeVisible()
  await expect(viewer.locator('mark').first()).toHaveText('HR: 44 bpm, regular')

  const jsonDownload = page.waitForEvent('download')
  await page.getByRole('link', { name: 'Download JSON' }).click()
  const json = await jsonDownload
  expect(json.suggestedFilename()).toBe(`aira-${runId}.json`)
  const exported = JSON.parse(await readFile(await json.path()!, 'utf-8'))
  expect(exported.run.run_id).toBe(runId)
  expect(
    exported.run.result.findings.map((f: { criterion_id: string; status: string }) => [
      f.criterion_id, f.status,
    ]),
  ).toEqual([
    ['criterion-telangiectasia', 'met'],
    ['criterion-perforator-reflux', 'missing'],
  ])

  const mdDownload = page.waitForEvent('download')
  await page.getByRole('link', { name: 'Download Markdown' }).click()
  const markdown = await mdDownload
  expect(markdown.suggestedFilename()).toBe(`aira-${runId}.md`)
})

test('contrary journey shows Not met, Conflicting, and the Contradicting relation', async ({ page }) => {
  await uploadBoth(page)
  await page.getByLabel('Procedure', { exact: true }).fill('E2E contrary')
  await submitAndWait(page)
  await expect(
    page.getByRole('heading', { name: 'Documentation gaps or contrary evidence' }),
  ).toBeVisible({ timeout: 20_000 })
  const notMetCard = page.getByLabel('Finding: criterion-telangiectasia')
  await expect(notMetCard.locator('.badge')).toHaveText('Not met')
  await expect(notMetCard.getByText('Contradicting:', { exact: true })).toBeVisible()
  const conflictingCard = page.getByLabel('Finding: criterion-perforator-reflux')
  await expect(conflictingCard.locator('.badge')).toHaveText('Conflicting')
  await expect(conflictingCard.getByText('Supporting:', { exact: true })).toBeVisible()
  await expect(conflictingCard.getByText('Contradicting:', { exact: true })).toBeVisible()
  await expect(conflictingCard.getByText(/disagree on symptom correlation/)).toBeVisible()
})

test('satisfied journey labels the satisfied outcome', async ({ page }) => {
  await uploadBoth(page)
  await page.getByLabel('Procedure', { exact: true }).fill('E2E satisfied')
  await submitAndWait(page)
  await expect(
    page.getByRole('heading', { name: 'Documented requirements satisfied' }),
  ).toBeVisible({ timeout: 20_000 })
  await expect(
    page.getByLabel('Finding: criterion-telangiectasia').locator('.badge'),
  ).toHaveText('Met')
})

test('alternative journey marks the unused OR branch without a documentation need', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByText(FIXTURE_NOTE)).toBeVisible()
  await page.getByLabel('Policy PDF').setInputFiles(POLICY_2026)
  await expect(page.getByText(/bcbs_fl_02-33000-31.*pages/)).toBeVisible()
  await page.getByLabel('Chart PDF').setInputFiles(CHART)
  await expect(page.getByText(/robert_mitchell_chart_final.*pages/)).toBeVisible()
  await page.getByLabel('Procedure', { exact: true }).fill('E2E alternative')
  await submitAndWait(page)
  await expect(
    page.getByRole('heading', { name: 'Documented requirements satisfied' }),
  ).toBeVisible({ timeout: 20_000 })
  const group = page.getByRole('heading', { name: /Any one of the following/ })
  await expect(group).toBeVisible()
  await expect(group.locator('.badge')).toHaveText('Satisfied')
  const metCard = page.getByLabel('Finding: criterion-telangiectasia')
  await expect(metCard.locator('.badge')).toHaveText('Met')
  await expect(metCard.getByText('Supports the satisfied path')).toBeVisible()
  const unused = page.getByLabel('Finding: criterion-perforator-reflux')
  await expect(unused.locator('.badge')).toHaveText('Missing')
  await expect(
    unused.getByText('Not needed — another alternative satisfies this group'),
  ).toBeVisible()
  await expect(unused.getByText('Documentation needed')).not.toBeVisible()

  const mdDownload = page.waitForEvent('download')
  await page.getByRole('link', { name: 'Download Markdown' }).click()
  const markdown = await mdDownload
  const text = await readFile(await markdown.path()!, 'utf-8')
  expect(text).toContain('alternative not needed')
})

test('clarify journey creates a linked child run and keeps the parent stopped', async ({ page }) => {
  await uploadBoth(page)
  await page.getByLabel('Procedure', { exact: true }).fill('E2E clarify')
  const parentRunId = await submitAndWait(page)
  await expect(page.getByText('Needs staff input', { exact: true })).toBeVisible({ timeout: 20_000 })
  await expect(page.getByText('Staff must identify the plan before scope resolves.')).toBeVisible()
  await expect(page.getByRole('group', { name: 'Plan' })).toBeVisible()

  await page.getByRole('group', { name: 'Plan' }).getByLabel('Value').fill('Fixture plan')
  await page.getByRole('button', { name: 'Submit clarification' }).click()

  await page.waitForURL(
    (url) => new URL(url.toString()).searchParams.get('run') !== parentRunId,
  )
  await expect(page.getByRole('link', { name: 'Previous attempt' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Documentation gaps or contrary evidence' })).toBeVisible({ timeout: 20_000 })
  await expect(page.getByText('Plan: Fixture plan')).toBeVisible()

  await page.goto(`/?run=${parentRunId}`)
  await expect(page.getByText('Needs staff input', { exact: true })).toBeVisible()
  const mdDownload = page.waitForEvent('download')
  await page.getByRole('link', { name: 'Download Markdown' }).click()
  const markdown = await mdDownload
  expect(markdown.suggestedFilename()).toBe(`aira-${parentRunId}.md`)
  const text = await readFile(await markdown.path()!, 'utf-8')
  expect(text).toContain('Assessment stopped for staff input')
})

test('a failed extraction explains the failure without an outcome banner', async ({ page }) => {
  await page.goto('/')
  await page.getByLabel('Policy PDF').setInputFiles(POLICY)
  await expect(page.getByText(/bcbs_fl_02-33000-31.*pages/)).toBeVisible()
  await page.getByLabel('Chart PDF').setInputFiles(IMAGE_ONLY)
  await expect(page.getByText(/image-only\.pdf.*pages/)).toBeVisible()
  await submitAndWait(page)
  await expect(page.getByText('Failed', { exact: true })).toBeVisible({ timeout: 20_000 })
  await expect(page.getByRole('alert')).toContainText(/not usable for native-text assessment/i)
  await expect(page.getByRole('alert')).toContainText(/extraction_failed/)
  await expect(page.getByRole('alert')).toContainText('Document: image-only.pdf')
  await expect(page.getByRole('alert')).toContainText(/Page 1 — Needs OCR/)
  await expect(page.getByRole('heading', { name: /does not apply|satisfied|gaps|Review required/ })).not.toBeVisible()
  await expect(page.getByText('Documentation readiness only — not an insurer decision.')).not.toBeVisible()
  await expect(page.getByRole('button', { name: 'Choose different documents' })).toBeVisible()
})

test('an encrypted chart is rejected at upload and start stays disabled', async ({ page }) => {
  await page.goto('/')
  await page.getByLabel('Policy PDF').setInputFiles(POLICY)
  await expect(page.getByText(/bcbs_fl_02-33000-31.*pages/)).toBeVisible()
  await page.getByLabel('Chart PDF').setInputFiles(ENCRYPTED)
  await expect(page.getByRole('alert')).toContainText(/password|encrypt/i)
  await expect(page.getByRole('button', { name: 'Start assessment' })).toBeDisabled()
})

test('a repeated request still cites the uploaded chart page', async ({ page }) => {
  await uploadBoth(page)
  await page.getByLabel('Procedure', { exact: true }).fill('E2E gaps')
  await submitAndWait(page)
  await expect(page.getByRole('heading', { name: 'Documentation gaps or contrary evidence' })).toBeVisible({ timeout: 20_000 })
  const metCard = page.getByLabel('Finding: criterion-telangiectasia')
  await metCard.getByRole('button', { name: /Chart, page 3/ }).click()
  const viewer = page.getByRole('complementary', { name: 'Source viewer' })
  await expect(viewer.locator('mark').first()).toHaveText('HR: 44 bpm, regular')

  await page.goto('/')
  await uploadBoth(page)
  await page.getByLabel('Procedure', { exact: true }).fill('E2E satisfied')
  await submitAndWait(page)
  await expect(page.getByRole('heading', { name: 'Documented requirements satisfied' })).toBeVisible({ timeout: 20_000 })
  const again = page.getByLabel('Finding: criterion-telangiectasia')
  await again.getByRole('button', { name: /Chart, page 3/ }).click()
  await expect(viewer.locator('mark').first()).toHaveText('HR: 44 bpm, regular')
  await expect(viewer.getByRole('heading', { name: /Page 3/ })).toBeVisible()
})

test('a reloaded run URL renders the same persisted outcome and findings', async ({ page }) => {
  await uploadBoth(page)
  await page.getByLabel('Procedure', { exact: true }).fill('E2E gaps')
  const runId = await submitAndWait(page)
  await expect(page.getByRole('heading', { name: 'Documentation gaps or contrary evidence' })).toBeVisible({ timeout: 20_000 })
  await page.goto(`/?run=${runId}`)
  await expect(page.getByRole('heading', { name: 'Documentation gaps or contrary evidence' })).toBeVisible({ timeout: 20_000 })
  await expect(
    page.getByLabel('Finding: criterion-telangiectasia').locator('.badge'),
  ).toHaveText('Met')
  await expect(
    page.getByLabel('Finding: criterion-perforator-reflux').locator('.badge'),
  ).toHaveText('Missing')
})
