import { execFileSync } from 'node:child_process'
import { mkdtemp, rm, rmdir } from 'node:fs/promises'
import { join } from 'node:path'
import { expect, test } from '@playwright/test'
import { assertBackendPortClosed, backendDir, backendService, healthUrl, python } from './backend-service.js'

const start = '2026-11-09T14:30:00Z'
const end = '2026-11-09T14:32:00Z'
const secondMinute = '2026-11-09T14:31:00Z'
const optionValue = timestamp => String(Date.parse(timestamp) / 1000)

function replayChart(page) {
  const region = page.getByRole('region', { name: 'Replay', exact: true })
  const details = region.locator('dl[aria-label="Market feed"]')
  return {
    region,
    status: region.getByRole('status', { name: 'Replay status' }),
    detail: label => details.locator('div').filter({ has: page.getByText(label, { exact: true }) }).locator('dd'),
    inspector: region.getByLabel('Inspect candle (UTC)'),
    values: region.locator('dl[aria-label="Selected candle"] dd'),
  }
}

function browserErrors(page) {
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  page.on('console', message => {
    if (message.type() === 'error') errors.push(message.text())
  })
  return errors
}

function fixture(action, path) {
  return JSON.parse(execFileSync(python, ['-B', '-m', 'tests.replay_fixture', action, path], {
    cwd: backendDir, encoding: 'utf8', windowsHide: true, timeout: 8000,
  }))
}

const replayTest = test.extend({
  replayBackend: [async ({}, use) => {
    const directory = await mkdtemp(join(backendDir, 'replay-smoke-'))
    const database = join(directory, 'observations.sqlite')
    const { startBackend, stopBackend } = backendService(
      'tests.replay_fixture:create_replay_test_app', ['--factory'], { REPLAY_TEST_DB: database },
    )
    try {
      await use({ database, startBackend })
    } finally {
      try {
        await stopBackend()
        await assertBackendPortClosed()
      } finally {
        await rm(database, { force: true })
        await rmdir(directory)
      }
    }
  }, { timeout: 15_000 }],
})

replayTest('replays the saved arrival sequence twice with Yahoo disconnected and SQLite unchanged', async ({ page, request, replayBackend }, testInfo) => {
  // Allow for Windows startup, the pause assertion, two runs and three SQLite inspections.
  testInfo.setTimeout(75_000)
  const { database, startBackend } = replayBackend
  const frames = []
  const external = []
  const socketPaths = []
  const errors = browserErrors(page)

  const { region, status, detail, inspector, values } = replayChart(page)
  const startInput = region.getByLabel('Start (UTC)', { exact: true })
  const endInput = region.getByLabel('End (UTC)', { exact: true })
  const speed = region.getByRole('combobox', { name: 'Playback speed', exact: true })
  const startReplay = region.getByRole('button', { name: 'Start replay', exact: true })

  page.on('request', request => {
    const url = new URL(request.url())
    if (['http:', 'https:'].includes(url.protocol) && url.hostname !== '127.0.0.1') external.push(url.hostname)
  })
  page.on('websocket', socket => {
    const url = new URL(socket.url())
    if (url.hostname !== '127.0.0.1') external.push(url.hostname)
    socketPaths.push(url.pathname)
    if (url.pathname === '/api/replay/stream') {
      socket.on('framereceived', ({ payload }) => frames.push(JSON.parse(payload)))
    }
  })

  async function expectFinalChart(evidence) {
    await expect(status).toContainText(/completed/i)
    await expect(detail('Observation ID')).toHaveText('6')
    await expect(detail('Original source time (UTC)')).toHaveText('2026-11-09T14:30:40.000000Z')
    await expect(detail('Original receipt time (UTC)')).toHaveText('2026-11-09T14:31:11.000000Z')
    await expect(inspector.locator('option')).toHaveCount(2)
    await inspector.selectOption(optionValue(start))
    await expect(values).toHaveText(['100', '105', '98', String(evidence.close), `${evidence.volume} shares`])
    const selectedStatus = region.locator('dl[aria-label="Selected candle status"] dd')
    await expect(selectedStatus.first()).toHaveText('Complete')
    await expect(selectedStatus.last()).toContainText('1/1 minutes')
    await inspector.selectOption(optionValue(secondMinute))
    await expect(values.last()).toHaveText('Unavailable')
  }

  function observedSteps(after = 0) {
    return frames.slice(after).filter(frame => frame.type === 'snapshot' && frame.replay_state === 'playing')
      .map(({ observation_id, source_time, receipt_time, candles, metadata }) => ({
        observation_id, source_time, receipt_time, candles, metadata,
      }))
  }

  const before = fixture('create', database)
  expect(before).toMatchObject({
    count: 6, schema_version: 1, current_minute_ids: [2, 5, 6], close: 105, volume: 0,
    baseline: 1000, closing_total: 1000,
  })
  await expect(request.get(healthUrl, { timeout: 1000 })).rejects.toThrow(/ECONN(?:REFUSED|RESET)/)
  await startBackend()

  await page.goto('/')
  await page.getByRole('button', { name: 'Open replay' }).click()
  await expect(detail('Data mode')).toHaveText('Replay')
  await expect(detail('Feed status')).toHaveText(/Recorded session\s+[—-]\s+live feed off/)
  await expect(region.getByLabel('Timeframe', { exact: true })).toBeDisabled()
  await expect(region.getByLabel('Recorded symbol and source')).toContainText('AAPL')
  await expect(startInput).not.toHaveValue('')
  await startInput.fill(start)
  await endInput.fill(end)
  await speed.selectOption('1')
  const replaySocketStart = socketPaths.length
  await startReplay.click()
  await expect(detail('Observation ID')).toHaveText('2')
  await region.getByRole('button', { name: 'Pause replay' }).click()
  await expect(status).toContainText(/paused/i)
  const pausedAt = observedSteps().length
  // Hold longer than the server's two-second maximum gap at 1×.
  await page.waitForTimeout(2200)
  expect(observedSteps()).toHaveLength(pausedAt)
  await speed.selectOption('4')
  await region.getByRole('button', { name: 'Resume replay' }).click()
  await expectFinalChart(before)

  const first = observedSteps()
  await expect(detail('Playback speed')).toHaveText(/^4[x×]$/)
  expect(first.map(frame => frame.observation_id)).toEqual([2, 3, 4, 5, 6])
  expect(first.map(frame => frame.candles[0].close)).toEqual([100, 100, 109, 98, 105])
  expect(first.map(frame => frame.candles[0].high)).toEqual([100, 100, 109, 109, 105])
  expect(first.at(-1).candles[0].low).toBe(98)
  expect(first.at(-1).candles[1].volume).toBeNull()
  expect(fixture('inspect', database)).toEqual(before)

  await region.getByRole('button', { name: 'Reset replay' }).click()
  await expect(status).toContainText(/ready/i)
  await expect(inspector).toHaveCount(0)
  const secondRunStart = frames.length
  await speed.selectOption('2')
  await startReplay.click()
  await expectFinalChart(before)
  await expect(detail('Playback speed')).toHaveText(/^2[x×]$/)
  expect(observedSteps(secondRunStart)).toEqual(first)
  expect(fixture('inspect', database)).toEqual(before)

  await startInput.fill('2026-11-09T14:40:00Z')
  await endInput.fill('2026-11-09T14:41:00Z')
  await startReplay.click()
  await expect(status).toHaveText('No recorded observations exist for this selection.')
  await expect(inspector).toHaveCount(0)
  expect(fixture('inspect', database)).toEqual(before)
  expect(socketPaths.slice(replaySocketStart)).toEqual(['/api/replay/stream', '/api/replay/stream'])
  expect(external).toEqual([])
  expect(errors).toEqual([])
  console.log(`Replay matched independent SQLite close ${before.close}, volume ${before.volume}. `
    + `Both runs preserved ${before.count} rows and SHA-256 ${before.sha256}.`)
})

test('replay retires old coverage responses and WebSocket updates', async ({ page }) => {
  const errors = browserErrors(page)
  const coverage = { available: true, recordings: [{ symbol: 'AAPL', source: 'constructed_test', start, end }] }
  const firstCoverage = Promise.withResolvers()
  const releaseCoverage = Promise.withResolvers()
  const finishedCoverage = Promise.withResolvers()
  const retired = []
  const sockets = []
  let coverageCalls = 0
  const { region, status, values } = replayChart(page)
  const startInput = region.getByLabel('Start (UTC)', { exact: true })
  const startReplay = region.getByRole('button', { name: 'Start replay', exact: true })
  const laterStart = '2026-11-09T14:30:01Z'

  const message = (selection, type, replay_state, extra = {}) => ({
    version: 1, type, data_mode: 'replay', feed_status: 'off', backend_status: 'connected',
    symbol: 'AAPL', source: 'constructed_test', interval: '1m', start: selection, end,
    as_of: selection, speed: 1, replay_state, position: 0, observation_id: null,
    source_time: null, receipt_time: null, volume_unit: 'shares', ...extra,
  })
  const snapshot = (selection, price) => message(selection, 'snapshot', 'playing', {
    position: 1, observation_id: price, source_time: selection, receipt_time: selection,
    candles: [{ timestamp: start, open: price, high: price, low: price, close: price, volume: 0 }],
    metadata: [{ timestamp: start, coverage: 'full', observed_minutes: 1, expected_minutes: 1, is_complete: false }],
  })

  await page.addInitScript(() => {
    const nativeFetch = window.fetch.bind(window)
    window.fetch = (input, options) => {
      if (new URL(input, window.location.href).pathname !== '/api/replay/coverage') return nativeFetch(input, options)
      // A response may already be in flight when the replay view is retired.
      return nativeFetch(input, { ...options, signal: undefined })
    }
    window.replayTestSockets = []
    const nativeAdd = EventTarget.prototype.addEventListener
    EventTarget.prototype.addEventListener = function (type, ...args) {
      if (type === 'message' && this instanceof WebSocket && new URL(this.url).pathname === '/api/replay/stream') {
        window.replayTestSockets.push(this)
      }
      return nativeAdd.call(this, type, ...args)
    }
  })
  await page.route(url => url.pathname === '/api/history', route => route.fulfill({
    json: { symbol: 'AAPL', interval: '1m', as_of: start, candles: [], metadata: [] },
  }))
  await page.routeWebSocket(/\/api\/market-feed\?/, () => {})
  await page.route(url => url.pathname === '/api/replay/coverage', async route => {
    coverageCalls++
    if (coverageCalls === 1) {
      firstCoverage.resolve()
      await releaseCoverage.promise
      try {
        await route.fulfill({ json: { ...coverage, recordings: [{ ...coverage.recordings[0], start: '2026-11-09T14:00:00Z' }] } })
      } finally {
        finishedCoverage.resolve()
      }
      return
    }
    await route.fulfill({ json: coverage })
  })
  await page.routeWebSocket(/\/api\/replay\/stream\?/, socket => {
    const selection = new URL(socket.url()).searchParams.get('start')
    sockets.push(socket)
    socket.onClose(() => retired.push(selection))
    socket.onMessage(data => {
      if (JSON.parse(data).action !== 'play') return
      socket.send(JSON.stringify(snapshot(selection, selection === start ? 100 : 105)))
      socket.send(JSON.stringify(message(selection, 'replay_status', 'completed')))
    })
    socket.send(JSON.stringify(message(selection, 'replay_status', 'ready')))
  })

  try {
    await page.goto('/')
    await page.getByRole('button', { name: 'Open replay' }).click()
    await firstCoverage.promise
    await page.getByRole('button', { name: 'Back to market candles' }).click()
    await page.getByRole('button', { name: 'Open replay' }).click()
    await expect(startInput).toHaveValue(start)
    releaseCoverage.resolve()
    await finishedCoverage.promise
    await expect(startInput).toHaveValue(start)
    await startReplay.click()
    await expect(status).toContainText(/completed/i)
    await expect(values.nth(3)).toHaveText('100')

    await startInput.fill(laterStart)
    await expect.poll(() => retired).toContain(start)
    await startReplay.click()
    await expect(status).toContainText(/completed/i)
    await expect(values.nth(3)).toHaveText('105')
    expect(sockets).toHaveLength(2)
    // Deliver a queued callback from the retired socket and a mismatched frame on the current one.
    await page.evaluate(data => {
      window.replayTestSockets[0].dispatchEvent(new MessageEvent('message', { data }))
    }, JSON.stringify(snapshot(start, 999)))
    sockets[1].send(JSON.stringify(snapshot(start, 999)))
    sockets[1].send(JSON.stringify(message(laterStart, 'replay_status', 'paused')))
    await expect(status).toContainText(/paused/i)
    await expect(startInput).toHaveValue(laterStart)
    await expect(values.nth(3)).toHaveText('105')
    expect(errors).toEqual([])
  } finally {
    releaseCoverage.resolve()
  }
})
