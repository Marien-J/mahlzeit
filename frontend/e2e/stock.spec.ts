import { expect, test, type Page } from '@playwright/test'

/**
 * M4 on a phone: one shop through 'Bought', three days of logging, a plausible purchased-versus-
 * logged report, a suggestion for a planned meal, and a pantry check of 30 items in under two
 * minutes.
 */
const code = process.env.E2E_STOCK_INVITE_CODE ?? ''
const run = Date.now().toString(36)
const password = 'a long e2e password'

test.skip(!code, 'E2E_STOCK_INVITE_CODE is not set; run scripts/e2e.sh')
test.use({ locale: 'de-DE', timezoneId: 'Europe/Berlin' })

async function shot(page: Page, name: string) {
  await page.screenshot({ path: `test-results/m4-${name}.png`, fullPage: true })
}

/** A calendar day in Berlin, `offset` days from today, as the app writes it. */
function day(offset: number): string {
  const d = new Date(Date.now() + offset * 86_400_000)
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Berlin' }).format(d)
}

/** Put a catalogue food on the list through the one field and its suggestions. */
async function listFood(page: Page, query: string, name: RegExp) {
  await page.getByLabel('Auf die Liste').fill(query)
  await page.getByRole('list', { name: 'Vorschläge' }).getByRole('button', { name }).first().click()
  await expect(page.getByRole('checkbox', { name })).toBeVisible()
}

async function addFood(page: Page, query: string, name: RegExp, grams: number, now: string) {
  await page.getByLabel('Lebensmittel suchen').fill(query)
  await page.getByTestId('results').getByRole('button', { name }).first().click()
  await page.getByLabel(/^Menge/).fill(String(grams))
  await page.getByRole('button', { name: now }).click()
}

const RICE = /Reis poliert/
const CHICKEN = /Hähnchen Brustfilet/

test('one shop, three days of logging, the report, suggestions and a pantry check', async ({
  page,
}) => {
  test.setTimeout(240_000)
  await page.goto('/join')
  await page.getByLabel('Einladungscode').fill(code)
  await page.getByRole('button', { name: 'Weiter' }).click()
  await page.getByLabel('Dein Name').fill('Jonas')
  await page.getByLabel('E-Mail').fill(`jonas-stock-${run}@example.org`)
  await page.getByLabel('Passwort').fill(password)
  await page.getByLabel('Name des Haushalts').fill(`Vorrat ${run}`)
  await page.getByRole('button', { name: 'Konto anlegen' }).click()
  await expect(page.getByRole('heading', { name: 'Heute' })).toBeVisible()

  // --- One shop: three things on the list, ticked off, then 'Bought' ---
  await page.getByRole('link', { name: 'Liste' }).click()
  await listFood(page, 'reis poliert', RICE)
  await listFood(page, 'hähnchen brustfilet', CHICKEN)
  await page.getByLabel('Auf die Liste').fill('Spülmittel')
  await page.getByLabel('Auf die Liste').press('Enter')
  for (const name of [RICE, CHICKEN, /Spülmittel/]) {
    await page.getByRole('checkbox', { name }).click()
  }
  await page.getByRole('button', { name: 'Gekauft' }).click()
  const bought = page.getByRole('dialog', { name: 'Gekauft' })
  await bought.getByLabel('Geschäft').selectOption({ label: 'ALDI' })
  await bought.getByLabel('Datum').fill(day(-2))
  await bought.getByLabel(/^Menge von Reis/).fill('1 kg')
  await bought.getByLabel(/^Preis von Reis/).fill('1,99')
  await bought.getByLabel(/^Menge von Hähnchen/).fill('600 g')
  await bought.getByLabel(/^Preis von Hähnchen/).fill('8,99')
  await bought.getByLabel('Preis von Spülmittel').fill('1,45')
  await shot(page, '1-bought')
  await bought.getByRole('button', { name: '3 Einträge bestätigen' }).click()
  await expect(page.getByRole('status')).toHaveText('3 Einträge gekauft')
  await expect(page.getByText('Die Liste ist leer.', { exact: false })).toBeVisible()

  // --- Three days of dinners from it ---
  for (const offset of [-2, -1, 0]) {
    await page.goto(`/add?day=${day(offset)}&slot=dinner&mode=search`)
    await addFood(page, 'reis poliert', RICE, 150, 'Weiteres hinzufügen')
    await addFood(page, 'hähnchen brustfilet', CHICKEN, 200, 'Jetzt eintragen')
    await expect(page.getByRole('button', { name: /Hähnchen Brustfilet/ }).first()).toBeVisible()
  }

  // --- Stock and the report ---
  await page.goto('/list')
  await page.getByRole('link', { name: 'Vorrat' }).click()
  const dry = page.getByRole('region', { name: 'Trockenware' })
  await expect(dry.getByRole('listitem').filter({ hasText: RICE })).toContainText('550 g')
  const meat = page.getByRole('region', { name: 'Fleisch und Fisch' })
  await expect(meat.getByRole('listitem').filter({ hasText: CHICKEN })).toContainText('0 g')
  await shot(page, '2-stock')

  await page.getByRole('link', { name: 'Gekauft und gegessen' }).click()
  const rice = page.getByRole('listitem', { name: RICE })
  await expect(rice).toContainText('Gekauft1 kg')
  await expect(rice).toContainText('Gegessen450 g')
  await expect(rice).toContainText('Noch da550 g')
  const chicken = page.getByRole('listitem', { name: CHICKEN })
  await expect(chicken).toContainText('Gekauft600 g')
  await expect(chicken).toContainText('Gegessen600 g')
  await expect(chicken).toContainText('Noch da0 g')
  await expect(page.getByText(/Ausgegeben: 12,43/)).toBeVisible()
  await shot(page, '3-report')

  // --- A meal planned for tomorrow: the list suggests what stock lacks ---
  await page.goto(`/add?day=${day(1)}&slot=dinner&plan=1&mode=search`)
  await addFood(page, 'hähnchen brustfilet', CHICKEN, 300, 'Planen')
  await page.goto('/list')
  const suggested = page.getByRole('region', { name: 'Vorgeschlagen' })
  await expect(suggested).toContainText('300 g')
  await suggested.getByRole('button', { name: /Hähnchen Brustfilet.*auf die Liste/ }).click()
  await expect(page.getByRole('checkbox', { name: CHICKEN })).toBeVisible()
  await expect(suggested).toHaveCount(0)
  await shot(page, '4-suggested')

  // --- 28 more things in stock (set up through the API), then the pantry check ---
  const me = await (await page.request.get('/api/auth/me')).json()
  const hits = (await (
    await page.request.get('/api/items', { params: { q: 'roh', limit: 80 } })
  ).json()) as { id: string; name: string; tracking_mode: string }[]
  const more = hits
    .filter((h) => !RICE.test(h.name) && !CHICKEN.test(h.name) && h.tracking_mode === 'counted')
    .slice(0, 28)
  expect(more).toHaveLength(28)
  const stocked = await page.request.post('/api/purchases', {
    headers: { 'X-CSRF-Token': me.csrf_token, Origin: new URL(page.url()).origin },
    data: {
      id: crypto.randomUUID(),
      lines: more.map((h) => ({ item_id: h.id, amount: 500 })),
    },
  })
  expect(stocked.status()).toBe(201)

  const start = Date.now()
  await page.goto('/stock')
  await expect(page.getByRole('heading', { name: 'Vorrat' })).toBeVisible()
  const aisles = page.locator('section.stock-aisle')
  await expect(aisles.first()).toBeVisible()
  const names = await aisles.evaluateAll((all) => all.map((a) => a.getAttribute('aria-label')))
  let items = 0
  for (const name of names) {
    const aisle = page.getByRole('region', { name: name ?? '' })
    items += await aisle.getByRole('listitem').count()
    await aisle.getByRole('button', { name: `${name} prüfen` }).click()
    // One fix per aisle with the stepper; the rest is right as it is.
    await aisle
      .getByRole('button', { name: /weniger$/ })
      .first()
      .click()
    if (name === names[0]) await shot(page, '5-checking')
    await aisle.getByRole('button', { name: `${name} als geprüft markieren` }).click()
    await expect(aisle.getByRole('button', { name: `${name} prüfen` })).toBeVisible()
  }
  const seconds = (Date.now() - start) / 1000
  console.log(`pantry check: ${items} items in ${names.length} aisles, ${seconds.toFixed(1)} s`)
  expect(items).toBeGreaterThanOrEqual(30)
  expect(seconds).toBeLessThan(120)
  for (const name of names) {
    await expect(page.getByRole('region', { name: name ?? '' })).toContainText('Geprüft am')
  }
  await shot(page, '6-pantry-checked')
})
