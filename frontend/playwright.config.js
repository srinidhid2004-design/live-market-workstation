import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './tests',
  workers: 1,
  timeout: 45_000,
  use: {
    channel: 'chrome',
    baseURL: 'http://127.0.0.1:5173',
  },
  globalSetup: './tests/vite-setup.js',
})
