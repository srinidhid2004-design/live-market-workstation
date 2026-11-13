import { fileURLToPath } from 'node:url'
import { createServer } from 'vite'

export default async function startVite() {
  // Keep the listener in the Playwright runner so a timed-out run cannot orphan a Vite child.
  const vite = await createServer({ root: fileURLToPath(new URL('../', import.meta.url)) })
  try {
    await vite.listen()
    const response = await fetch('http://127.0.0.1:5173/', { signal: AbortSignal.timeout(5000) })
    if (!response.ok) throw new Error(`Vite readiness returned HTTP ${response.status}.`)
    await response.arrayBuffer()
  } catch (error) {
    await vite.close()
    throw error
  }
  return () => vite.close()
}
