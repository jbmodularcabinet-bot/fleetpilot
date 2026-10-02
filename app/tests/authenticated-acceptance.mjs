import assert from 'node:assert/strict'
import { pathToFileURL } from 'node:url'

const modulePath = process.env.CREATIVEOS_PLAYWRIGHT_MODULE
const { chromium } = await import(modulePath ? pathToFileURL(modulePath).href : 'playwright')
const fixture = JSON.parse(process.env.CREATIVEOS_ACCEPTANCE_FIXTURE)

async function launchAcceptanceBrowser() {
  const requested = process.env.CREATIVEOS_ACCEPTANCE_BROWSER_CHANNEL?.trim()
  const candidates = requested ? [requested] : (process.platform === 'win32' ? ['msedge', 'chrome', null] : ['chrome', null])
  const failures = []
  for (const channel of candidates) {
    try {
      const candidate = await chromium.launch({ headless: true, ...(channel ? { channel } : {}) })
      const page = await candidate.newPage()
      const codecs = await page.evaluate(() => ({
        h264: document.createElement('video').canPlayType('video/mp4; codecs=avc1.42E01E'),
        aac: document.createElement('audio').canPlayType('audio/mp4; codecs=mp4a.40.2'),
      }))
      await page.close()
      if (codecs.h264 && codecs.aac) {
        console.log('Acceptance browser:', channel || 'bundled chromium', codecs)
        return candidate
      }
      failures.push((channel || 'bundled chromium') + ': H.264/AAC unsupported')
      await candidate.close()
    } catch (error) {
      failures.push((channel || 'bundled chromium') + ': ' + String(error?.message || error).split('\n')[0])
    }
  }
  throw new Error('No H.264/AAC-capable acceptance browser available. ' + failures.join(' | '))
}

const browser = await launchAcceptanceBrowser()
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
    if (process.env.CREATIVEOS_ACCEPTANCE_LOGIN_SCREENSHOT && account === fixture.accounts[0])
      await page.screenshot({ path: process.env.CREATIVEOS_ACCEPTANCE_LOGIN_SCREENSHOT, fullPage: true })
    await page.getByLabel('Username', { exact: true }).fill(account.username)
    await page.getByLabel('Password', { exact: true }).fill(account.password)
    await page.getByRole('button', { name: 'Sign in', exact: true }).click()
    await page.getByLabel('Organization', { exact: true }).selectOption(account.org)
    await page.getByLabel('Brand / product', { exact: true }).selectOption(account.brand)
    await page.getByRole('button', { name: /Creative Intelligence/i }).click()
    await page.getByRole('heading', { name: 'Evidence before generation.', exact: true }).waitFor()
    await page.locator('.platform-symbol').evaluate(img => { if (!img.complete || img.naturalWidth === 0) throw Error('Approved CreativeOS brand symbol not loaded') })

    const ciObjective = account.username + ' evidence-backed hypothesis'
    const ciVariant = account.username + ' variant A'
    const ciObservation = account.username + ' observed proof after governed production'
    await page.getByLabel('Market subject', { exact: true }).fill(account.username + ' service')
    await page.getByLabel('Evidence source', { exact: true }).fill('Authenticated acceptance fixture')
    await page.getByLabel('Market notes', { exact: true }).fill('Observed customer uncertainty before production.')
    await page.getByRole('button', { name: 'Save intelligence', exact: true }).click()
    await page.getByText('Observed customer uncertainty before production.', { exact: true }).waitFor()
    await page.getByLabel('Hypothesis objective', { exact: true }).fill(ciObjective)
    await page.getByLabel('Hypothesis hook', { exact: true }).fill('Evidence before generation')
    await page.getByRole('button', { name: 'Create hypothesis', exact: true }).click()
    await page.locator('.ci-list article').filter({ hasText: ciObjective }).first().waitFor()
    await page.getByLabel('Experiment hypothesis', { exact: true }).selectOption({ label: ciObjective })
    await page.getByLabel('Experiment variant', { exact: true }).fill(ciVariant)
    await page.getByRole('button', { name: 'Create experiment', exact: true }).click()
    await page.locator('.ci-list article').filter({ hasText: ciVariant }).first().waitFor()
    if (process.env.CREATIVEOS_ACCEPTANCE_DASHBOARD_SCREENSHOT && account === fixture.accounts[0])
      await page.screenshot({ path: process.env.CREATIVEOS_ACCEPTANCE_DASHBOARD_SCREENSHOT, fullPage: true })
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

    await page.getByLabel('Evidence hypothesis', { exact: true }).selectOption({ label: ciObjective })
    await page.getByLabel('Evidence source name', { exact: true }).fill('Governed browser acceptance')
    await page.getByLabel('Evidence observation', { exact: true }).fill(ciObservation)
    await page.getByLabel('Evidence sample size', { exact: true }).fill('1')
    await page.getByRole('button', { name: 'Attach evidence', exact: true }).click()
    await page.getByText(ciObservation, { exact: true }).waitFor()
    await page.getByLabel('Asset experiment', { exact: true }).selectOption({ label: ciVariant })
    const assetSelect = page.getByLabel('Existing asset', { exact: true })
    const firstAsset = await assetSelect.locator('option').nth(1).getAttribute('value')
    assert.ok(firstAsset, 'Existing generated asset must be available after governed production')
    await assetSelect.selectOption(firstAsset)
    assert.match(await assetSelect.locator('option:checked').innerText(), /(REAL PROJECT|APPROVED RENDER|AI DERIVED|AI GENERATED|UNCLASSIFIED)/)
    await page.getByRole('button', { name: 'Link asset', exact: true }).click()
    await page.getByText(/1 linked asset\(s\)/i).waitFor()

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
    report.push(account.username + ': sign in -> organization -> brand -> Market Intelligence -> Hypothesis -> Experiment -> campaign -> strategy -> storyboard -> MOCK generation -> real render QA PASS -> human review -> export/download -> Evidence -> existing asset link PASS')
    if (fixture.screenshot) await page.screenshot({ path: fixture.screenshot, fullPage: true })
    if (process.env.CREATIVEOS_ACCEPTANCE_MOBILE_SCREENSHOT && account === fixture.accounts[0]) {
      await page.setViewportSize({ width: 390, height: 844 })
      await page.screenshot({ path: process.env.CREATIVEOS_ACCEPTANCE_MOBILE_SCREENSHOT, fullPage: true })
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), 'Mobile layout must not overflow horizontally')
      await page.setViewportSize({ width: 1440, height: 1100 })
    }
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
