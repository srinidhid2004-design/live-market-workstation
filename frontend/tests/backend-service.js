import { execFileSync, spawn } from 'node:child_process'
import { get } from 'node:http'
import { createConnection } from 'node:net'
import { join } from 'node:path'
import { setTimeout as delay } from 'node:timers/promises'
import { fileURLToPath } from 'node:url'

export const backendDir = fileURLToPath(new URL('../../backend/', import.meta.url))
export const python = join(backendDir, '.venv', 'Scripts', 'python.exe')
export const healthUrl = 'http://127.0.0.1:8000/api/health'
const healthyBody = Buffer.from('{"status":"healthy"}')
const networkErrors = new Set(['ECONNREFUSED', 'ECONNRESET', 'EACCES', 'ETIMEDOUT'])

function healthProbe(milliseconds) {
  return new Promise(resolve => {
    const signal = AbortSignal.timeout(milliseconds)
    const fail = error => resolve(signal.aborted ? 'request timeout' : (
      networkErrors.has(error.code) ? error.code : 'local HTTP error'
    ))
    const request = get(healthUrl, { agent: false, signal }, response => {
      response.on('error', fail)
      if (response.statusCode !== 200) {
        resolve(`HTTP ${response.statusCode}`)
        response.destroy()
        return
      }
      let offset = 0
      response.on('data', chunk => {
        const end = offset + chunk.length
        if (end > healthyBody.length || !chunk.equals(healthyBody.subarray(offset, end))) {
          resolve('unexpected health body')
          response.destroy()
          return
        }
        offset = end
      })
      response.on('end', () => resolve(offset === healthyBody.length ? null : 'unexpected health body'))
    })
    request.on('error', fail)
  })
}

function waitForClose(closed, milliseconds) {
  let timer
  const deadline = new Promise(resolve => { timer = setTimeout(() => resolve(false), milliseconds) })
  return Promise.race([closed, deadline]).finally(() => clearTimeout(timer))
}

export function assertBackendPortClosed() {
  return new Promise((resolve, reject) => {
    const socket = createConnection({ host: '127.0.0.1', port: 8000, timeout: 1000 })
    socket.once('connect', () => {
      socket.destroy()
      reject(new Error('Port 8000 still accepts connections.'))
    })
    socket.once('timeout', () => socket.destroy(new Error('Port 8000 shutdown check timed out.')))
    socket.once('error', error => {
      if (['ECONNREFUSED', 'ECONNRESET'].includes(error.code)) resolve()
      else reject(error)
    })
  })
}

export function backendService(app = 'app.main:app', extraArgs = [], extraEnv = {}) {
  let child
  let closed

  async function startBackend() {
    child = spawn(python, [
      '-B', '-m', 'uvicorn', app, ...extraArgs,
      '--host', '127.0.0.1', '--port', '8000', '--timeout-graceful-shutdown', '2',
    ], {
      cwd: backendDir, stdio: ['ignore', 'inherit', 'inherit'], windowsHide: true,
      env: { ...process.env, ...extraEnv },
    })
    closed = new Promise(resolve => child.once('close', () => resolve(true)))
    let spawnFailed = false
    child.once('error', () => { spawnFailed = true })
    const deadline = performance.now() + 10_000
    let lastError = 'no health response'
    while (performance.now() < deadline) {
      if (spawnFailed || child.exitCode !== null || child.signalCode !== null) {
        const reason = spawnFailed ? 'process launch failed' : 'process exited'
        throw new Error(`Backend startup failed (${reason}, last probe: ${lastError}).`)
      }
      const remaining = Math.ceil(deadline - performance.now())
      if (remaining <= 0) break
      const result = await healthProbe(Math.min(1000, remaining))
      if (result === null) return
      lastError = result
      const wait = Math.min(100, deadline - performance.now())
      if (wait > 0) await delay(wait)
    }
    throw new Error(`Backend readiness timed out after 10 seconds (last probe: ${lastError}).`)
  }

  async function stopBackend() {
    if (!child) return
    const running = child.pid && child.exitCode === null && child.signalCode === null
    if (running) {
      if (process.platform === 'win32') {
        // Node cannot reliably signal a hidden Windows venv interpreter through its launcher.
        try {
          execFileSync('taskkill.exe', ['/PID', String(child.pid), '/T', '/F'], {
            stdio: 'ignore', windowsHide: true, timeout: 3000,
          })
        } catch {
          if (!await waitForClose(closed, 2000)) throw new Error('Could not stop the owned backend process tree.')
        }
      } else {
        child.kill('SIGTERM')
        if (!await waitForClose(closed, 4000)) child.kill('SIGKILL')
      }
    }
    if (!await waitForClose(closed, 2000)) throw new Error('The test backend did not exit.')
    child = undefined
    await assertBackendPortClosed()
  }

  return { startBackend, stopBackend }
}
