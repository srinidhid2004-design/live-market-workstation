import { execFileSync } from 'node:child_process'
import { mkdtemp, rm } from 'node:fs/promises'
import { join } from 'node:path'
import { expect, test } from '@playwright/test'
import { backendDir, backendService, healthUrl as backendUrl, python } from './backend-service.js'

const expectedBody = '{"status":"healthy"}'

test('local connection shows health, backend outage, and recovery', async ({ page, request }) => {
  const { startBackend, stopBackend } = backendService()
  const pageErrors = []
  const consoleErrors = []
  page.on('pageerror', (error) => pageErrors.push(error.message))
  page.on('console', (message) => {
    if (message.type() === 'error') {
      consoleErrors.push({ text: message.text(), url: message.location().url })
    }
  })

  async function expectHealth(url) {
    const response = await request.get(url)
    expect(response.status()).toBe(200)
    expect(await response.text()).toBe(expectedBody)
    console.log(`${url} HTTP 200 ${expectedBody}`)
  }

  try {
    await expect(request.get(backendUrl, { timeout: 1000 })).rejects.toThrow(/ECONNREFUSED/)
    await startBackend()
    await expectHealth(backendUrl)
    await expectHealth('http://127.0.0.1:5173/api/health')

    await page.goto('/')
    const sample = page.getByRole('region', { name: 'Synthetic one-minute sample' })
    const chart = sample.getByRole('img', { name: 'Candlestick price and volume chart' })
    await expect(chart).toBeVisible()
    const feedDetails = sample.locator('dl[aria-label="Market feed"]')
    await expect(feedDetails.locator('div').filter({ hasText: 'WebSocket' }).locator('dd')).toHaveText('Connected')
    await expect(feedDetails.locator('div').filter({ hasText: 'Feed status' }).locator('dd')).toHaveText('Unavailable')
    await expect(sample.getByRole('link', { name: 'TradingView' }))
      .toHaveAttribute('href', 'https://www.tradingview.com/')

    // Read the rendered canvas layers to verify separate candle bodies and aligned volume bars.
    await expect.poll(() => chart.locator('canvas').evaluateAll((canvases) => {
      const positions = { up: new Set(), down: new Set(), volume: new Set() }
      const plotWidth = Math.max(0, ...canvases.map((canvas) => canvas.width))
      for (const canvas of canvases) {
        if (!plotWidth || canvas.width !== plotWidth || !canvas.height) continue
        const { data } = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height)
        for (let i = 0; i < data.length; i += 4) {
          if (data[i + 3] !== 255) continue
          const x = (i / 4) % canvas.width
          const rgb = (data[i] << 16) | (data[i + 1] << 8) | data[i + 2]
          if (rgb === 0x087f72) positions.up.add(x)
          if (rgb === 0xb84045) positions.down.add(x)
          if (rgb === 0x638ca5) positions.volume.add(x)
        }
      }
      const down = [...positions.down].sort((a, b) => a - b)
      if (down.length < 2) return false
      const left = [...positions.up].filter((x) => x < down[0])
      const right = [...positions.up].filter((x) => x > down.at(-1))
      return [left, down, right].every((body) => {
        if (body.length < 2) return false
        const center = Math.round((Math.min(...body) + Math.max(...body)) / 2)
        return positions.volume.has(center)
      })
    })).toBe(true)

    const inspect = sample.getByLabel('Inspect candle (UTC)')
    const unknownVolumeTime = '2026-11-09T14:30:00Z'
    const zeroVolumeTime = '2026-11-09T14:31:00Z'
    const unknownVolumeOption = String(Date.parse(unknownVolumeTime) / 1000)
    const zeroVolumeOption = String(Date.parse(zeroVolumeTime) / 1000)
    await expect(inspect.locator('option')).toHaveCount(3)
    await expect(inspect.locator('option').nth(0)).toHaveText(/9 November 2026.*14:30 UTC/)
    await expect(inspect.locator('option').nth(1)).toHaveText(/9 November 2026.*14:31 UTC/)
    await inspect.selectOption(zeroVolumeOption)
    const values = sample.locator('dl[aria-label="Selected candle"] dd')
    await expect(values).toHaveText(['102', '104', '100', '101', '850 shares'])
    console.log('Chrome showed distinct candles and aligned volume. 14:31 UTC close 101, volume 850 shares.')

    await page.route((url) => url.pathname === '/api/history', async (route) => {
      const response = await route.fetch()
      const history = await response.json()
      history.candles.find(({ timestamp }) => timestamp === unknownVolumeTime).volume = null
      history.candles.find(({ timestamp }) => timestamp === zeroVolumeTime).volume = 0
      await route.fulfill({ response, json: history })
    }, { times: 1 })
    // Handle the socket locally without connecting upstream or sending a snapshot.
    await page.routeWebSocket(/\/api\/market-feed\?/, () => {})
    await page.reload()
    await inspect.selectOption(unknownVolumeOption)
    await expect(inspect).toHaveValue(unknownVolumeOption)
    await expect(values).toHaveText(['100', '103', '99', '102', 'Unavailable'])
    await inspect.selectOption(zeroVolumeOption)
    await expect(inspect).toHaveValue(zeroVolumeOption)
    await expect(values.nth(3)).toHaveText('101')
    await expect(values.last()).toHaveText('0 shares')

    const button = page.getByRole('button', { name: 'Check connection' })
    const status = page.getByRole('status')

    let releaseRequest
    const heldRequest = new Promise((resolve) => { releaseRequest = resolve })
    await page.route('**/api/health', async (route) => {
      await heldRequest
      await route.continue()
    }, { times: 1 })
    try {
      await button.click()
      await expect(button).toBeDisabled()
      await expect(status).toContainText('Checking connection')
    } finally {
      releaseRequest()
    }
    await expect(status).toContainText('Backend is healthy.')
    await expect(status).toContainText('HTTP 200')
    await expect(status).toContainText(expectedBody)
    await expect(button).toBeEnabled()
    console.log('Chrome displayed the pending and healthy states.')

    await stopBackend()
    await expect(request.get(backendUrl, { timeout: 1000 })).rejects.toThrow(/ECONN(?:REFUSED|RESET)/)
    const outage = await request.get('/api/health')
    expect(outage.status()).toBeGreaterThanOrEqual(500)
    const browserResponse = page.waitForResponse((response) => new URL(response.url()).pathname === '/api/health')
    await button.click()
    expect((await browserResponse).status()).toBe(outage.status())
    await expect(status).toContainText('Backend unavailable.')
    await expect(status).toContainText(`HTTP ${outage.status()}`)
    await expect(status).not.toContainText(expectedBody)
    console.log(`Proxy HTTP ${outage.status()} with Uvicorn stopped. Chrome displayed backend unavailable.`)

    await startBackend()
    await expectHealth(backendUrl)
    await expectHealth('http://127.0.0.1:5173/api/health')
    await button.click()
    await expect(status).toContainText('HTTP 200')
    await expect(status).toContainText(expectedBody)
    console.log('Chrome displayed the healthy state after restart.')

    const applicationConsoleErrors = consoleErrors.filter(
      ({ text, url }) => !(url.endsWith('/api/health') && text.includes(String(outage.status()))),
    )
    expect(pageErrors).toEqual([])
    expect(applicationConsoleErrors).toEqual([])
    console.log(`Chrome console: no application errors, ${consoleErrors.length} expected failed-resource errors.`)
  } finally {
    await stopBackend()
  }
})

test('recorded input updates chart through FastAPI and reports upstream recovery', async ({ page, request }) => {
  const directory = await mkdtemp(join(backendDir, 'market-feed-smoke-'))
  const database = join(directory, 'observations.sqlite')
  const { startBackend, stopBackend } = backendService('tests.market_feed_demo:create_demo_app', ['--factory'], {
    MARKET_FEED_TEST_DB: database,
  })
  const errors = []
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text())
  })
  const market = page.getByRole('region', { name: 'Market candles' })
  const details = market.locator('dl[aria-label="Market feed"]')
  const detail = (label) => details.locator('div').filter({ has: page.getByText(label, { exact: true }) }).locator('dd')
  const inspect = market.getByLabel('Inspect candle (UTC)')
  const selected = market.locator('dl[aria-label="Selected candle"] dd')
  const completion = market.locator('dl[aria-label="Selected candle status"] dd').first()

  async function trigger(action) {
    const result = await request.post(`http://127.0.0.1:8000/api/demo-feed?action=${action}`)
    expect(result.status()).toBe(202)
  }

  try {
    await expect(request.get(backendUrl, { timeout: 1000 })).rejects.toThrow(/ECONN(?:REFUSED|RESET)/)
    await startBackend()
    await page.goto('/')
    await expect(market.getByLabel('Timeframe')).toHaveValue('1m')
    await expect(detail('Source')).toHaveText('Constructed test data')
    await expect(detail('Data mode')).toHaveText('Recorded')
    await expect(detail('Feed status')).toHaveText('Recorded input')
    await expect(detail('WebSocket')).toHaveText('Connected')
    await expect(detail('Observation ID')).toHaveText('1')
    await expect(inspect.locator('option')).toHaveCount(1)
    await expect(selected).toHaveText(['100', '100', '100', '100', 'Unavailable'])
    await expect(completion).toHaveText('Forming')

    await trigger('update')
    await expect(selected).toHaveText(['100', '103', '100', '103', 'Unavailable'])
    await expect(inspect.locator('option')).toHaveCount(1)
    await expect(detail('Update source time (UTC)')).toHaveText('2026-11-09T14:30:30Z')
    await expect(detail('Backend receipt time (UTC)')).toHaveText('2026-11-09T14:30:30Z')
    await expect(detail('Observation ID')).toHaveText('2')

    const persisted = JSON.parse(execFileSync(python, ['-B', '-c', [
      'import json, pathlib, sqlite3, sys',
      'uri = pathlib.Path(sys.argv[1]).resolve().as_uri() + "?mode=ro"',
      'with sqlite3.connect(uri, uri=True) as db:',
      '    query = "SELECT observation_id, source_time_utc, receipt_time_utc, price FROM observations WHERE observation_id = ?"',
      '    print(json.dumps(db.execute(query, (2,)).fetchone()))',
    ].join('\n'), database], { encoding: 'utf8', windowsHide: true, timeout: 5000 }))
    expect(persisted[0]).toBe(2)
    expect(Date.parse(persisted[1])).toBe(Date.parse('2026-11-09T14:30:30Z'))
    expect(Date.parse(persisted[2])).toBe(Date.parse('2026-11-09T14:30:30Z'))
    expect(persisted[3]).toBe(103)

    await trigger('fail')
    await expect(detail('Feed status')).toHaveText('Unavailable')
    await expect(detail('WebSocket')).toHaveText('Connected')
    await expect(selected.nth(3)).toHaveText('103')

    await trigger('recover')
    await expect(detail('Feed status')).toHaveText('Recorded input')
    await expect(inspect.locator('option')).toHaveCount(2)
    await expect(completion).toHaveText('Complete')
    await inspect.selectOption({ index: 1 })
    await expect(selected.nth(3)).toHaveText('104')
    await expect(completion).toHaveText('Forming')
    expect(errors).toEqual([])
  } finally {
    await stopBackend()
    await rm(directory, { recursive: true, force: true })
  }
})

test('timeframe changes discard delayed requests and retired socket updates', async ({ page }) => {
  const seenHistory = []
  const seenSockets = []
  const retiredSockets = []
  const sockets = new Map()
  const pendingDaily = Promise.withResolvers()
  const releaseDaily = Promise.withResolvers()
  const timestamp = '2026-11-09T14:30:00Z'
  const prices = { '1m': 100, '5m': 500, '15m': 150, '1h': 60, '1d': 900 }
  const candle = (close) => ({ timestamp, open: close, high: close, low: close, close, volume: null })
  const metadata = {
    timestamp, coverage: 'partial', observed_minutes: 1, expected_minutes: 5, is_complete: false,
  }
  const history = (interval) => ({
    symbol: 'AAPL', interval, as_of: '2026-11-09T14:31:30Z', source: 'constructed_test', data_mode: 'recorded',
    candles: [candle(prices[interval])], metadata: [metadata],
  })
  const envelope = (interval, type) => ({
    version: 1, type, symbol: 'AAPL', interval, source: 'constructed_test', data_mode: 'recorded',
    feed_status: 'recorded', latest_source_time: timestamp, source_time: timestamp,
    receipt_time: '2026-11-09T14:30:01Z', age_seconds: 90, observation_id: 1,
  })
  const chart = page.getByRole('region', { name: 'Market candles' })
  const timeframe = chart.getByLabel('Timeframe')
  const close = chart.locator('dl[aria-label="Selected candle"] dd').nth(3)
  const volume = chart.locator('dl[aria-label="Selected candle"] dd').last()
  const details = chart.locator('dl[aria-label="Market feed"]')
  const transport = details.locator('div').filter({ hasText: 'WebSocket' }).locator('dd')
  const feedStatus = details.locator('div').filter({ hasText: 'Feed status' }).locator('dd')
  const errors = []
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text())
  })

  await page.route((url) => url.pathname === '/api/history', async (route) => {
    const query = new URL(route.request().url()).searchParams
    const interval = query.get('interval')
    seenHistory.push([query.get('symbol'), interval])
    if (interval === '1d' && seenHistory.filter(([, value]) => value === '1d').length === 1) {
      pendingDaily.resolve()
      await releaseDaily.promise
    }
    await route.fulfill({ json: history(interval) })
  })
  await page.routeWebSocket(/\/api\/market-feed\?/, (socket) => {
    const query = new URL(socket.url()).searchParams
    const interval = query.get('interval')
    seenSockets.push([query.get('symbol'), interval])
    sockets.set(interval, socket)
    socket.onClose(() => retiredSockets.push(interval))
    socket.send(JSON.stringify({ ...history(interval), ...envelope(interval, 'snapshot') }))
  })

  try {
    await page.goto('/')
    await expect(timeframe).toHaveValue('1m')
    await expect(close).toHaveText('100')
    await expect(transport).toHaveText('Connected')

    await timeframe.selectOption('1d')
    await pendingDaily.promise
    expect(seenSockets).toEqual([['AAPL', '1m']])
    await timeframe.selectOption('5m')
    await expect(close).toHaveText('500')
    await expect(transport).toHaveText('Connected')
    await expect.poll(() => retiredSockets).toContain('1m')
    releaseDaily.resolve()
    sockets.get('5m').send(JSON.stringify({
      ...envelope('1m', 'candle_upsert'), candle: candle(999), metadata,
    }))
    sockets.get('5m').send(JSON.stringify({ ...envelope('5m', 'feed_status'), feed_status: 'stale' }))
    await expect(details).toContainText('Stale')
    await expect(close).toHaveText('500')
    sockets.get('5m').send(JSON.stringify({
      ...envelope('5m', 'candle_upsert'), candle: { ...candle(505), volume: 5 }, metadata,
    }))
    await expect(volume).toHaveText('5')
    sockets.get('5m').send(JSON.stringify({
      ...envelope('5m', 'candle_upsert'), candle: candle(510), metadata,
    }))
    await expect(close).toHaveText('510')
    await expect(volume).toHaveText('Unavailable')
    expect(seenHistory).toEqual([['AAPL', '1m'], ['AAPL', '1d'], ['AAPL', '5m']])
    expect(seenSockets).toEqual([['AAPL', '1m'], ['AAPL', '5m']])

    sockets.get('5m').close()
    await expect(transport).toHaveText('Disconnected')
    await expect(feedStatus).toHaveText('Unknown')
    await expect(close).toHaveText('510')
    await expect(transport).toHaveText('Connected')
    expect(seenSockets).toEqual([['AAPL', '1m'], ['AAPL', '5m'], ['AAPL', '5m']])
    await expect(close).toHaveText('500')

    await timeframe.selectOption('1d')
    await expect(close).toHaveText('900')
    await expect(transport).toHaveText('Connected')
    expect(seenSockets.at(-1)).toEqual(['AAPL', '1d'])
    expect(errors).toEqual([])
  } finally {
    releaseDaily.resolve()
  }
})
