import { spawn } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { expect, test } from '@playwright/test'

const backendDir = fileURLToPath(new URL('../../backend/', import.meta.url))
const python = fileURLToPath(
  new URL('../../backend/.venv/Scripts/python.exe', import.meta.url),
)
const backendUrl = 'http://127.0.0.1:8000/api/health'
const expectedBody = '{"status":"healthy"}'

test('local connection shows health, backend outage, and recovery', async ({ page, request }) => {
  let backend
  let backendClosed
  const pageErrors = []
  const consoleErrors = []

  page.on('pageerror', (error) => pageErrors.push(error.message))
  page.on('console', (message) => {
    if (message.type() === 'error') {
      consoleErrors.push({ text: message.text(), url: message.location().url })
    }
  })

  async function startBackend() {
    backend = spawn(python, ['-B', '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000'], {
      cwd: backendDir,
      stdio: 'inherit',
      windowsHide: true,
    })
    const child = backend
    backendClosed = new Promise((resolve) => {
      child.once('close', resolve)
    })
    let spawnError
    child.once('error', (error) => { spawnError = error })
    await expect.poll(async () => {
      if (spawnError) throw spawnError
      if (child.exitCode !== null) throw new Error('Uvicorn exited during startup.')
      try {
        return (await request.get(backendUrl, { timeout: 1000 })).status()
      } catch {
        return 0
      }
    }, { timeout: 10_000 }).toBe(200)
  }

  async function stopBackend() {
    if (!backend) return
    backend.kill()
    await backendClosed
    backend = undefined
  }

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
    await expect(inspect.locator('option')).toHaveCount(3)
    await expect(inspect.locator('option').nth(0)).toHaveText(/9 November 2026.*14:30 UTC/)
    await expect(inspect.locator('option').nth(1)).toHaveText(/9 November 2026.*14:31 UTC/)
    await inspect.selectOption({ index: 1 })
    const values = sample.locator('dl dd')
    await expect(values).toHaveText(['102', '104', '100', '101', '850 shares'])
    console.log('Chrome showed distinct candles and aligned volume. 14:31 UTC close 101, volume 850 shares.')

    await page.route('**/api/history', async (route) => {
      const response = await route.fetch()
      const history = await response.json()
      history.candles[0].volume = null
      history.candles[1].volume = 0
      await route.fulfill({ response, json: history })
    }, { times: 1 })
    await page.reload()
    await expect(values.last()).toHaveText('Unavailable')
    await inspect.selectOption({ index: 1 })
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
