#!/usr/bin/env node
/** Capture a real local or deployed homepage without API stubs or parsing requests. */
import { createHash } from 'node:crypto'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { dirname, isAbsolute, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const repository = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const argumentsList = process.argv.slice(2)
const options = { baseUrl: 'http://127.0.0.1:12303/', outputDir: resolve(repository, 'docs/assets') }
for (let index = 0; index < argumentsList.length; index += 2) {
  const flag = argumentsList[index]
  const value = argumentsList[index + 1]
  if (!value || !['--base-url', '--output-dir'].includes(flag)) {
    throw new Error('Usage: capture_brand_screenshots.mjs [--base-url URL] [--output-dir PATH]')
  }
  if (flag === '--base-url') options.baseUrl = new URL(value).href
  else options.outputDir = resolve(value)
}

const moduleLocation = process.env.PLAYWRIGHT_MODULE || 'playwright-core'
const { chromium } = await import(isAbsolute(moduleLocation) ? pathToFileURL(moduleLocation).href : moduleLocation)
const browser = await chromium.launch({
  headless: true,
  ...(process.env.CHROMIUM_EXECUTABLE ? { executablePath: process.env.CHROMIUM_EXECUTABLE } : {}),
  args: ['--no-proxy-server'],
})
const captures = [
  { name: 'desktop', width: 1440, height: 1060, isMobile: false },
  { name: 'mobile', width: 390, height: 1285, isMobile: true },
]
const report = { baseUrl: options.baseUrl, capturedAt: new Date().toISOString(), browser: browser.version(), captures: [] }

try {
  await mkdir(options.outputDir, { recursive: true })
  for (const capture of captures) {
    const { name, width, height, isMobile } = capture
    const context = await browser.newContext({
      viewport: { width, height },
      deviceScaleFactor: 1,
      isMobile,
      hasTouch: isMobile,
      locale: 'zh-CN',
      timezoneId: 'Asia/Shanghai',
      colorScheme: 'light',
      reducedMotion: 'reduce',
      serviceWorkers: 'block',
    })
    try {
      const page = await context.newPage()
      const pageErrors = []
      const nonReadRequests = []
      page.on('pageerror', (error) => pageErrors.push(error.message))
      page.on('request', (request) => {
        if (!['GET', 'HEAD', 'OPTIONS'].includes(request.method())) nonReadRequests.push(request.method())
      })
      const response = await page.goto(options.baseUrl, { waitUntil: 'networkidle', timeout: 45_000 })
      if (!response?.ok()) throw new Error(`Homepage returned HTTP ${response?.status()}`)
      await page.locator('h1').filter({ hasText: 'MO-Parse' }).waitFor()
      await page.locator('.header-refresh:not([disabled])').waitFor({ timeout: 45_000 })
      await page.locator('.workspace-state-art').first().waitFor()
      await page.evaluate(async () => {
        await document.fonts.ready
        await Promise.all([...document.images].map((image) => image.decode()))
        window.scrollTo(0, 0)
      })
      const state = await page.evaluate(() => ({
        serviceStatus: document.querySelector('.service-summary')?.textContent?.trim(),
        images: [...document.images].map((image) => ({
          source: image.currentSrc,
          width: image.naturalWidth,
          height: image.naturalHeight,
        })),
        horizontalOverflow: document.documentElement.scrollWidth > window.innerWidth + 1,
      }))
      if (pageErrors.length) throw new Error(`Page errors: ${pageErrors.join('; ')}`)
      if (nonReadRequests.length) throw new Error(`Unexpected write requests: ${nonReadRequests.join(', ')}`)
      if (state.horizontalOverflow) throw new Error(`${name} page exceeds its viewport width`)
      const path = resolve(options.outputDir, `mo-parse-web-${name}.png`)
      await page.screenshot({ path, fullPage: false, animations: 'disabled' })
      const sha256 = createHash('sha256').update(await readFile(path)).digest('hex')
      report.captures.push({ name, viewport: { width, height }, path, sha256, ...state })
    } finally {
      await context.close()
    }
  }
  const reportText = `${JSON.stringify(report, null, 2)}\n`
  await writeFile(resolve(options.outputDir, 'capture-report.json'), reportText)
  process.stdout.write(reportText)
} finally {
  await browser.close()
}
