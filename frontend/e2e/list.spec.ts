import { expect, test, type Browser, type Locator, type Page } from '@playwright/test'

/**
 * M2 on two phones: a change on one shows on the other within 3 seconds, and a shop done in
 * airplane mode (the app even reopened offline) syncs cleanly afterwards, without duplicates.
 */
const code = process.env.E2E_LIST_INVITE_CODE ?? ''
const run = Date.now().toString(36)
const password = 'a long e2e password'

test.skip(!code, 'E2E_LIST_INVITE_CODE is not set; run scripts/e2e.sh')

async function shot(page: Page, name: string) {
  await page.screenshot({ path: `test-results/m2-${name}.png`, fullPage: true })
}

async function phone(browser: Browser): Promise<Page> {
  const context = await browser.newContext({ locale: 'de-DE', timezoneId: 'Europe/Berlin' })
  return context.newPage()
}

async function add(page: Page, text: string) {
  await page.getByLabel('Auf die Liste').fill(text)
  await page.getByLabel('Auf die Liste').press('Enter')
}

/** The visible list as [text, checked] pairs, top to bottom. */
async function rows(page: Page): Promise<[string, boolean][]> {
  const boxes = page.getByRole('checkbox')
  const result: [string, boolean][] = []
  for (const box of await boxes.all()) {
    result.push([
      (await box.getAttribute('aria-label')) ?? '',
      (await box.getAttribute('aria-checked')) === 'true',
    ])
  }
  return result
}

async function seen(locator: Locator, start: number): Promise<number> {
  await expect(locator).toBeVisible({ timeout: 10_000 })
  return Date.now() - start
}

test('live on two phones, and a shop in airplane mode syncs cleanly', async ({ browser }) => {
  test.setTimeout(120_000)
  // --- Jonas starts a household and invites Sam ---
  const a = await phone(browser)
  await a.goto('/join')
  await a.getByLabel('Einladungscode').fill(code)
  await a.getByRole('button', { name: 'Weiter' }).click()
  await a.getByLabel('Dein Name').fill('Jonas')
  await a.getByLabel('E-Mail').fill(`jonas-list-${run}@example.org`)
  await a.getByLabel('Passwort').fill(password)
  await a.getByLabel('Name des Haushalts').fill(`Liste ${run}`)
  await a.getByRole('button', { name: 'Konto anlegen' }).click()
  await expect(a.getByRole('heading', { name: 'Heute' })).toBeVisible()
  await a.getByRole('link', { name: 'Haushalt' }).click()
  await a.getByRole('button', { name: 'Einladung erstellen' }).click()
  const link = ((await a.getByTestId('invite-link').textContent()) ?? '').trim()

  const b = await phone(browser)
  await b.goto(new URL(link).pathname)
  await b.getByLabel('Dein Name').fill('Sam')
  await b.getByLabel('E-Mail').fill(`sam-list-${run}@example.org`)
  await b.getByLabel('Passwort').fill(password)
  await b.getByRole('button', { name: 'Konto anlegen' }).click()
  await expect(b.getByRole('heading', { name: 'Heute' })).toBeVisible()

  // --- Both open the list ---
  await a.getByRole('link', { name: 'Liste' }).click()
  await b.getByRole('link', { name: 'Liste' }).click()
  await expect(a.getByText('Die Liste ist leer.', { exact: false })).toBeVisible()
  await expect(b.getByText('Die Liste ist leer.', { exact: false })).toBeVisible()

  // --- Live: an add on A shows on B, a check on B shows on A, each within 3 s ---
  const timings: number[] = []
  let start = Date.now()
  await add(a, '2 Milch')
  timings.push(await seen(b.getByRole('checkbox', { name: 'Milch' }), start))
  for (const text of ['Brot', 'Äpfel', 'Spülmittel', 'Käse']) await add(a, text)
  await expect(b.getByRole('checkbox')).toHaveCount(5)
  start = Date.now()
  await b.getByRole('checkbox', { name: 'Milch' }).click()
  timings.push(
    await seen(a.locator('[role="checkbox"][aria-label="Milch"][aria-checked="true"]'), start),
  )
  console.log(`live sync: ${timings.map((t) => `${t} ms`).join(', ')}`)
  for (const t of timings) expect(t).toBeLessThan(3000)
  await shot(b, '1-live')

  // --- Sam goes shopping in airplane mode; the app even reopens offline ---
  await b.context().setOffline(true)
  await b.reload()
  await expect(b.getByRole('checkbox', { name: 'Brot' })).toBeVisible()
  await b.getByRole('button', { name: 'Einkaufen' }).click()
  await b.getByRole('checkbox', { name: 'Brot' }).click()
  await b.getByRole('checkbox', { name: 'Äpfel' }).click()
  await b.getByRole('button', { name: 'Fertig' }).click()
  await add(b, 'Kaffee')
  await b.getByRole('button', { name: 'Käse' }).click()
  await b.getByRole('button', { name: 'Von der Liste nehmen' }).click()
  await expect(b.getByTestId('pending')).toContainText('4 Änderungen warten')
  await shot(b, '2-offline')

  // Meanwhile, at home, Jonas adds eggs and changes the washing-up liquid.
  await add(a, '10 Eier')
  await a.getByRole('button', { name: 'Spülmittel' }).click()
  await a.getByLabel('Menge').fill('2')
  await a.getByRole('button', { name: 'Speichern' }).click()

  // --- Back online: the queue goes out, both phones agree, nothing twice ---
  await b.context().setOffline(false)
  await expect(b.getByTestId('pending')).toHaveCount(0)
  const expected: [string, boolean][] = [
    ['Spülmittel', false],
    ['Eier', false],
    ['Kaffee', false],
  ]
  await expect.poll(async () => (await rows(b)).filter(([, done]) => !done)).toEqual(expected)
  await expect.poll(async () => (await rows(a)).filter(([, done]) => !done)).toEqual(expected)
  const checked = async (p: Page) =>
    (await rows(p))
      .filter(([, done]) => done)
      .map(([text]) => text)
      .sort()
  await expect.poll(() => checked(a)).toEqual(['Brot', 'Milch', 'Äpfel'])
  await expect.poll(() => checked(b)).toEqual(['Brot', 'Milch', 'Äpfel'])
  await expect(b.getByRole('button', { name: /Spülmittel/ })).toContainText('2')
  await b.reload()
  expect((await rows(b)).length).toBe(6)
  await shot(b, '3-synced')
  await shot(a, '3-synced-other-phone')
})
