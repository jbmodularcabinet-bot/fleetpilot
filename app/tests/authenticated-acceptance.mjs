import assert from 'node:assert/strict'
import { pathToFileURL } from 'node:url'

const modulePath = process.env.CREATIVEOS_PLAYWRIGHT_MODULE
const { chromium } = await import(modulePath ? pathToFileURL(modulePath).href : 'playwright')
const fixture = JSON.parse(process.env.CREATIVEOS_ACCEPTANCE_FIXTURE)
const browser = await chromium.launch({ headless: true })
const contexts = []
const errors = []
const report = []
try {
  for (const account of fixture.accounts) {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1100 }, acceptDownloads: true })
    contexts.push(context)
    const page = await context.newPage()
    page.on('pageerror', error => errors.push(error.message))
    await page.goto(fixture.base)
    await page.getByLabel('Username', { exact: true }).fill(account.username)
    await page.getByLabel('Password', { exact: true }).fill(account.password)
    await page.getByRole('button', { name: 'Sign in', exact: true }).click()
    await page.getByLabel('Organization', { exact: true }).selectOption(account.org)
    await page.getByLabel('Brand / product', { exact: true }).selectOption(account.brand)
    await page.getByLabel('Title', { exact: true }).fill(account.username + ' private campaign')
    await page.getByLabel('Objective', { exact: true }).fill('Explore this independent product')
    await page.getByLabel('Audience', { exact: true }).fill('Business teams')
    await page.getByLabel('Offer', { exact: true }).fill('Discover our product')
    await page.getByLabel('Call to action', { exact: true }).fill('Learn more')
    await page.getByRole('button', { name: 'Create campaign', exact: true }).click()
    await page.getByRole('heading', { name: account.username + ' private campaign', exact: true }).waitFor()
    await page.getByRole('button', { name: 'Generate strategy', exact: true }).click()
    await page.getByRole('button', { name: 'Approve plan and storyboard', exact: true }).click()
    await page.getByRole('button', { name: 'Generate local MOCK preview', exact: true }).click()
    await page.getByText('Generation stage: 6 / 10', { exact: true }).waitFor({ timeout: 60000 })
    await page.getByRole('button', { name: 'View generated preview', exact: true }).click()
    await page.locator('video').waitFor()
    await page.waitForFunction(() => document.querySelector('video')?.readyState >= 2)
    assert.ok(await page.locator('video').evaluate(video => video.duration > 1))
    await page.getByRole('button', { name: 'Run QA', exact: true }).click()
    await page.getByText('QA result: PASS', { exact: true }).waitFor()
    await page.getByLabel('Review note', { exact: true }).fill('Reviewed local MOCK preview in browser acceptance')
    await page.getByRole('button', { name: 'Accept preview', exact: true }).click()
    await page.getByRole('button', { name: 'Export approved preview', exact: true }).click()
    const downloading = page.waitForEvent('download')
    await page.getByRole('button', { name: 'Download approved export', exact: true }).click()
    const download = await downloading
    assert.equal(await download.failure(), null)
    const state = await page.evaluate(async () => {
      const session = await (await fetch('/api/session')).json()
      const workspace = await (await fetch('/api/workspace', { headers: { 'X-Scope-Version': String(session.version) } })).json()
      const campaign = workspace.campaigns[0]
      const detail = await (await fetch('/api/campaigns/' + campaign.id, { headers: { 'X-Scope-Version': String(session.version) } })).json()
      return { session, workspace, detail }
    })
    account.campaign = state.detail.campaign.id
    account.request = state.detail.generation_requests[0].id
    account.export = state.detail.export_jobs[0].id
    account.records = ['generation_queue', 'qa_runs', 'qa_reviews', 'generation_approvals', 'generation_spend_ledger'].flatMap(table =>
      state.detail[table].map(row => [table, row.id]))
    assert.equal(state.workspace.campaigns.length, 1)
    assert.equal(state.workspace.brand.id, account.brand)
    assert.ok(!JSON.stringify(state.workspace.brand).includes('FleetPilot'))
    assert.ok(!JSON.stringify(state.workspace.brand).includes('HABI'))
    report.push(account.username + ': sign in -> organization -> brand -> campaign -> strategy -> storyboard -> MOCK generation -> real render QA PASS -> human review -> export/download PASS')
    if (fixture.screenshot) await page.screenshot({ path: fixture.screenshot, fullPage: true })
  }
  for (let i = 0; i < 2; i++) {
    const page = contexts[i].pages()[0]
    const foreign = fixture.accounts[1-i]
    const results = await page.evaluate(async ({ foreign }) => {
      const session = await (await fetch('/api/session')).json()
      const headers = { 'X-Scope-Version': String(session.version), 'X-CSRF-Token': session.csrf, 'Content-Type': 'application/json' }
      const targets = [
        ['GET', '/api/campaigns/' + foreign.campaign],
        ['POST', '/api/requests/' + foreign.request + '/qa'],
        ['POST', '/api/requests/' + foreign.request + '/review'],
        ['POST', '/api/requests/' + foreign.request + '/export'],
        ['GET', '/api/requests/' + foreign.request + '/preview'],
        ['GET', '/api/exports/' + foreign.export + '/download'],
        ...foreign.records.map(([table, id]) => ['GET', '/api/records/' + table + '/' + id]),
      ]
      const statuses = []
      for (const [method, path] of targets) statuses.push((await fetch(path, { method, headers, body: method === 'POST' ? JSON.stringify({ decision: 'ACCEPTED', note: 'forged' }) : undefined })).status)
      statuses.push((await fetch('/api/context', { method: 'POST', headers, body: JSON.stringify({ organization_id: foreign.org, brand_profile_id: foreign.brand }) })).status)
      return statuses
    }, { foreign })
    assert.ok(results.every(status => status === 403), JSON.stringify(results))
  }
  report.push('Bidirectional foreign campaign, queue, QA, approval, cost, preview, export and forged selection probes: all denied')
  const first = contexts[0].pages()[0]
  const tab = await contexts[0].newPage()
  await tab.goto(fixture.base)
  await tab.getByLabel('Brand / product', { exact: true }).selectOption(fixture.accounts[0].secondBrand)
  await first.waitForFunction(id => document.querySelector('select[aria-label="Brand / product"]')?.value === id, fixture.accounts[0].secondBrand)
  assert.equal(await first.getByRole('heading', { name: fixture.accounts[0].username + ' private campaign', exact: true }).count(), 0)
  assert.equal(await first.locator('video').count(), 0)
  assert.equal(await first.getByRole('button', { name: 'Download approved export', exact: true }).count(), 0)
  await tab.reload()
  await tab.waitForFunction(id => document.querySelector('select[aria-label="Brand / product"]')?.value === id, fixture.accounts[0].secondBrand)
  assert.equal(await tab.getByLabel('Brand / product', { exact: true }).inputValue(), fixture.accounts[0].secondBrand)
  const crossBrand = await tab.evaluate(async id => {
    const session = await (await fetch('/api/session')).json()
    return (await fetch('/api/campaigns/' + id, { headers: { 'X-Scope-Version': String(session.version) } })).status
  }, fixture.accounts[0].campaign)
  assert.equal(crossBrand, 403)
  report.push('Cross-tab brand switch cleared old campaign/media/export; reload persisted server context; cross-brand read denied')
  await tab.getByRole('button', { name: 'Inspect unowned legacy records', exact: true }).click()
  await tab.getByRole('button', { name: 'Preview adoption of Legacy Independent', exact: true }).click()
  const confirm = tab.getByRole('button', { name: 'Confirm ownership adoption', exact: true })
  assert.equal(await confirm.isDisabled(), true)
  await tab.getByRole('checkbox').check()
  await confirm.click()
  await tab.getByLabel('Brand / product', { exact: true }).selectOption(fixture.legacyBrand)
  await tab.getByRole('button', { name: 'Legacy campaign', exact: true }).waitFor()
  report.push('Legacy preview displayed destination/counts; confirmation disabled until explicit checkbox; adopted brand became selectable')
  assert.deepEqual(errors, [])
  console.log(JSON.stringify({ status: 'PASS', checks: report, browserErrors: errors }, null, 2))
} finally {
  await browser.close()
}
