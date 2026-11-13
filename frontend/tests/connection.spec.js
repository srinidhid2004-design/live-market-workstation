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
