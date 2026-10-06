import { chromium, devices, expect, test, type Page } from '@playwright/test'
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

/**
 * M0 smoke test on a phone viewport: a new household joins by invite, the partner joins by
 * link, both use the app in their language, and the PWA is installable and opens offline.
 */
const code = process.env.E2E_INVITE_CODE ?? ''
const run = Date.now().toString(36)
const password = 'a long e2e password'
const jonas = { name: 'Jonas', email: `jonas-${run}@example.org` }
const sam = { name: 'Sam', email: `sam-${run}@example.org` }

test.skip(!code, 'E2E_INVITE_CODE is not set; run scripts/e2e.sh')

async function shot(page: Page, name: string) {
  await page.screenshot({ path: `test-results/m0-${name}.png`, fullPage: true })
}

test('two people join, switch language, and the app opens offline', async ({ browser }) => {
  // --- Jonas starts a household with the admin's invite code (German UI) ---
  const jonasContext = await browser.newContext({ locale: 'de-DE' })
  const a = await jonasContext.newPage()
  await a.goto('/join')
  await a.getByLabel('Einladungscode').fill(code)
  await a.getByRole('button', { name: 'Weiter' }).click()
  await expect(a.getByText('Du bist eingeladen, einen eigenen Haushalt')).toBeVisible()
  await a.getByLabel('Dein Name').fill(jonas.name)
  await a.getByLabel('E-Mail').fill(jonas.email)
  await a.getByLabel('Passwort').fill(password)
  await a.getByLabel('Name des Haushalts').fill(`Zuhause ${run}`)
  await a.getByRole('button', { name: 'Konto anlegen' }).click()
  await expect(a.getByRole('heading', { name: 'Hallo, Jonas' })).toBeVisible()
  await shot(a, '1-jonas-today-de')

  // --- Jonas invites a partner ---
  await a.getByRole('link', { name: 'Haushalt' }).click()
  await a.getByRole('button', { name: 'Einladung erstellen' }).click()
  const link = ((await a.getByTestId('invite-link').textContent()) ?? '').trim()
  expect(link).toMatch(/\/join\/[\w-]{20,}$/)
  await shot(a, '2-jonas-invite')

  // --- Sam opens the link on another phone and picks Dutch ---
  const samContext = await browser.newContext({ locale: 'de-DE' })
  const b = await samContext.newPage()
  await b.goto(new URL(link).pathname)
  await expect(b.getByText(`Jonas lädt dich in den Haushalt „Zuhause ${run}“ ein.`)).toBeVisible()
  await b.getByLabel('Sprache').selectOption('nl')
  await b.getByLabel('Je naam').fill(sam.name)
  await b.getByLabel('E-mail').fill(sam.email)
  await b.getByLabel('Wachtwoord').fill(password)
  await b.getByRole('button', { name: 'Account aanmaken' }).click()
  await expect(b.getByRole('heading', { name: 'Hallo, Sam' })).toBeVisible()
  await expect(b.getByRole('link', { name: 'Vandaag' })).toBeVisible()
  await shot(b, '3-sam-today-nl')

  // --- Sam switches to English; it sticks after a reload ---
  await b.getByRole('link', { name: 'Instellingen' }).click()
  await b.getByLabel('Taal').selectOption('en')
  await expect(b.getByRole('heading', { name: 'Settings' })).toBeVisible()
  await b.reload()
  await expect(b.getByRole('heading', { name: 'Settings' })).toBeVisible()
  await shot(b, '4-sam-settings-en')

  // --- Jonas sees Sam in the household ---
  await a.reload()
  await expect(a.getByText('Sam', { exact: true })).toBeVisible()
  await expect(a.getByText('Offene Einladungen')).toHaveCount(0)

  // --- Jonas signs out and back in ---
  await a.getByRole('link', { name: 'Einstellungen' }).click()
  await a.getByRole('button', { name: 'Abmelden' }).click()
  await expect(a.getByRole('heading', { name: 'Anmelden' })).toBeVisible()
  await a.getByLabel('E-Mail').fill(jonas.email)
  await a.getByLabel('Passwort').fill(password)
  await a.getByRole('button', { name: 'Anmelden' }).click()
  await expect(a.getByRole('heading', { name: 'Hallo, Jonas' })).toBeVisible()

  // --- The service worker takes control after the first load ---
  await a.evaluate(() => navigator.serviceWorker.ready)
  await a.reload()
  expect(await a.evaluate(() => navigator.serviceWorker.controller !== null)).toBe(true)

  // --- Offline: the app shell still opens from the service worker ---
  await jonasContext.setOffline(true)
  await a.reload()
  await expect(a.getByText('Du bist offline.')).toBeVisible()
  await expect(a.getByRole('heading', { name: 'Hallo, Jonas' })).toBeVisible()
  await shot(a, '5-jonas-offline')
  await jonasContext.setOffline(false)

  await jonasContext.close()
  await samContext.close()
})

test('Chrome reports the PWA as installable', async ({ baseURL }) => {
  // Install is never offered in incognito, which every normal Playwright context is,
  // so this check uses a persistent profile.
  const profile = mkdtempSync(join(tmpdir(), 'mahlzeit-pwa-'))
  const { viewport, userAgent, deviceScaleFactor, isMobile, hasTouch } = devices['Pixel 7']
  const context = await chromium.launchPersistentContext(profile, {
    viewport,
    userAgent,
    deviceScaleFactor,
    isMobile,
    hasTouch,
    baseURL,
    executablePath: process.env.PW_CHROMIUM_PATH,
  })
  try {
    const page = await context.newPage()
    await page.goto('/login')
    await page.evaluate(() => navigator.serviceWorker.ready)
    await page.reload()
    const cdp = await context.newCDPSession(page)
    const manifest = (await cdp.send('Page.getAppManifest')) as { errors: unknown[]; url: string }
    expect(manifest.url).toMatch(/manifest\.webmanifest$/)
    expect(manifest.errors).toEqual([])
    const result = (await cdp.send('Page.getInstallabilityErrors')) as {
      installabilityErrors: unknown[]
    }
    expect(result.installabilityErrors).toEqual([])
    await shot(page, '6-login-installable')
  } finally {
    await context.close()
    rmSync(profile, { recursive: true, force: true })
  }
})
