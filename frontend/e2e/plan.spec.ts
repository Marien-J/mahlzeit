import { expect, test, type Browser, type Locator, type Page } from '@playwright/test'

/**
 * M3 on two phones: a week of dinners planned from staple recipes, then an offer that is
 * countered and accepted, shares set by feel, a meal eaten for both with one tap, a meal dragged
 * into a new order, and a recipe's ingredients on the shopping list. Every change shows on the
 * other phone without reloading.
 */
const code = process.env.E2E_PLAN_INVITE_CODE ?? ''
const run = Date.now().toString(36)
const password = 'a long e2e password'

test.skip(!code, 'E2E_PLAN_INVITE_CODE is not set; run scripts/e2e.sh')

async function shot(page: Page, name: string) {
  await page.screenshot({ path: `test-results/m3-${name}.png`, fullPage: true })
}

async function phone(browser: Browser): Promise<Page> {
  const context = await browser.newContext({ locale: 'de-DE', timezoneId: 'Europe/Berlin' })
  return context.newPage()
}

/** A calendar day in Berlin, `offset` days from today, as the app writes it. */
function day(offset: number): string {
  const d = new Date(Date.now() + offset * 86_400_000)
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Berlin' }).format(d)
}

async function createRecipe(page: Page, name: string, foods: [string, string][]) {
  await page.goto('/recipes')
  await page.getByRole('button', { name: 'Neues Rezept' }).click()
  const form = page.getByRole('dialog', { name: 'Neues Rezept' })
  await form.getByLabel('Name', { exact: true }).fill(name)
  await form.getByLabel('Portionen').fill('4')
  for (const [query, grams] of foods) {
    await form.getByRole('button', { name: 'Zutat hinzufügen' }).click()
    const picker = page.getByRole('dialog', { name: 'Zutat hinzufügen' })
    await picker.getByLabel('Zutat suchen').fill(query)
    await picker
      .getByRole('button')
      .filter({ hasText: new RegExp(query, 'i') })
      .first()
      .click()
    await form
      .getByLabel(/^Menge von/)
      .last()
      .fill(grams)
  }
  await form.getByRole('switch', { name: 'Standardrezept' }).check()
  await form.getByRole('button', { name: 'Speichern' }).click()
  await expect(page.getByRole('button', { name: new RegExp(name) })).toBeVisible()
}

/** Plan a dinner on the plan page from a staple recipe, for both of us. */
async function planDinner(page: Page, offset: number, recipe: string) {
  await page.goto('/plan')
  const row = page.getByTestId(`plan-${day(offset)}`)
  await row.getByRole('link', { name: /Mahlzeit planen für/ }).click()
  await expect(page.getByRole('heading', { name: 'Mahlzeit planen' })).toBeVisible()
  await page.getByRole('switch', { name: 'Gemeinsam essen' }).check()
  await page
    .getByRole('button', { name: new RegExp(recipe) })
    .first()
    .click()
  await page.getByRole('dialog', { name: recipe }).getByRole('button', { name: 'Planen' }).click()
  await expect(page.getByRole('heading', { name: 'Plan', exact: true })).toBeVisible()
}

/** The card of a meal on the day view (not its drag handle or its "eaten" button). */
function card(page: Page, name: string): Locator {
  return page.getByRole('button', { name: new RegExp(`^\\d\\d:\\d\\d.*${name}`) }).first()
}

async function entryOrder(page: Page, names: string[]): Promise<string[]> {
  const found: { name: string; y: number }[] = []
  for (const name of names) {
    const box = await card(page, name).boundingBox()
    if (box) found.push({ name, y: box.y })
  }
  return found.sort((a, b) => a.y - b.y).map((f) => f.name)
}

async function drag(page: Page, handle: Locator, target: () => Locator) {
  const from = await handle.boundingBox()
  if (!from) throw new Error('no drag handle')
  await page.mouse.move(from.x + from.width / 2, from.y + from.height / 2)
  await page.mouse.down()
  await page.mouse.move(from.x + 40, from.y + 40, { steps: 8 })
  const zone = target()
  await expect(zone).toBeVisible()
  const to = await zone.boundingBox()
  if (!to) throw new Error('no drop zone')
  await page.mouse.move(to.x + to.width / 2, to.y + to.height / 2, { steps: 12 })
  await page.mouse.up()
}

test('a week of dinners, an offer countered and accepted, shares, eaten, order, list', async ({
  browser,
}) => {
  test.setTimeout(240_000)
  // --- Jonas starts a household and invites Sam ---
  const a = await phone(browser)
  await a.goto('/join')
  await a.getByLabel('Einladungscode').fill(code)
  await a.getByRole('button', { name: 'Weiter' }).click()
  await a.getByLabel('Dein Name').fill('Jonas')
  await a.getByLabel('E-Mail').fill(`jonas-plan-${run}@example.org`)
  await a.getByLabel('Passwort').fill(password)
  await a.getByLabel('Name des Haushalts').fill(`Plan ${run}`)
  await a.getByRole('button', { name: 'Konto anlegen' }).click()
  await expect(a.getByRole('heading', { name: 'Heute' })).toBeVisible()
  await a.getByRole('link', { name: 'Haushalt' }).click()
  await a.getByRole('button', { name: 'Einladung erstellen' }).click()
  const link = ((await a.getByTestId('invite-link').textContent()) ?? '').trim()

  const b = await phone(browser)
  await b.goto(new URL(link).pathname)
  await b.getByLabel('Dein Name').fill('Sam')
  await b.getByLabel('E-Mail').fill(`sam-plan-${run}@example.org`)
  await b.getByLabel('Passwort').fill(password)
  await b.getByRole('button', { name: 'Konto anlegen' }).click()
  await expect(b.getByRole('heading', { name: 'Heute' })).toBeVisible()

  // --- Staple recipes ---
  await createRecipe(a, 'Chili', [
    ['hähnchen brustfilet', '400'],
    ['reis', '200'],
  ])
  await createRecipe(a, 'Curry', [
    ['hähnchen brustfilet', '400'],
    ['reis', '200'],
  ])
  await shot(a, '1-recipes')

  // --- A week of dinners, planned by both of us, tomorrow onwards ---
  const week = Array.from({ length: 7 }, (_, i) => i + 1)
  for (const offset of week) {
    await planDinner(offset % 2 === 1 ? a : b, offset, offset % 2 === 1 ? 'Chili' : 'Curry')
  }
  await a.goto('/plan')
  await b.goto('/plan')
  for (const offset of week) {
    for (const p of [a, b]) {
      await expect(p.getByTestId(`plan-${day(offset)}`)).toContainText(
        offset % 2 === 1 ? 'Chili' : 'Curry',
      )
      await expect(p.getByTestId(`plan-${day(offset)}`)).toContainText(
        p === a ? 'Jonas & Sam' : 'Sam & Jonas',
      )
    }
  }
  await shot(b, '2-week')

  // --- An offer: Jonas plans a dinner for today and offers it to Sam ---
  await a.goto('/add?plan=1&mode=quick&slot=dinner')
  await a.getByLabel('Was war es?').fill('Pasta')
  await a.getByRole('button', { name: 'Planen' }).click()
  await expect(a.getByRole('heading', { name: 'Heute' })).toBeVisible()
  await a.getByRole('button', { name: /Abendessen.*Pasta/ }).click()
  await a.getByRole('button', { name: 'Anbieten' }).click()
  await a
    .getByRole('dialog', { name: 'Sam anbieten' })
    .getByRole('button', { name: 'Angebot senden' })
    .click()
  await expect(a.getByText('Wartet auf Sam')).toBeVisible()

  // Sam sees it without reloading: the card, and a badge on the Today tab.
  await b.goto('/')
  const offer = b.getByTestId('offer')
  await expect(offer).toContainText('Jonas bietet dir eine Mahlzeit an', { timeout: 10_000 })
  await expect(b.getByLabel('1 Angebot wartet')).toBeVisible()
  await shot(b, '3-offer')

  // Sam counters with something else; Jonas sees the counter-offer and accepts it.
  await offer.getByRole('button', { name: 'Anderes vorschlagen' }).click()
  const counter = b.getByRole('dialog', { name: 'Gegenvorschlag an Jonas' })
  await counter.getByLabel('Oder nur ein Name').fill('Linsensuppe')
  await counter.getByRole('button', { name: 'Vorschlagen' }).click()
  await expect(a.getByText('Sam schlägt etwas anderes vor')).toBeVisible({ timeout: 10_000 })
  await a.getByRole('button', { name: 'Annehmen' }).click()

  // The meal is now one dish across both columns, on both phones, and Pasta is gone.
  for (const p of [a, b]) {
    await expect(p.getByTestId('joint-row')).toContainText('Linsensuppe', { timeout: 10_000 })
    await expect(p.getByTestId('joint-row')).toContainText(
      p === a ? 'Jonas 50 % · Sam 50 %' : 'Sam 50 % · Jonas 50 %',
    )
    await expect(p.getByText('Pasta')).toHaveCount(0)
  }
  await shot(a, '4-accepted')

  // --- Shares by feel, then eaten with one tap on the card ---
  await a.getByRole('button', { name: /Abendessen.*Linsensuppe/ }).click()
  const sheet = a.getByRole('dialog', { name: 'Linsensuppe' })
  await sheet.getByRole('button', { name: '75 %' }).click()
  await sheet.getByRole('button', { name: 'Anteil übernehmen' }).click()
  await expect(b.getByTestId('joint-row')).toContainText('Sam 25 % · Jonas 75 %', {
    timeout: 10_000,
  })
  await sheet.getByRole('button', { name: 'Schließen' }).click()
  await a.getByRole('button', { name: 'Linsensuppe als gegessen markieren' }).click()
  await expect(b.getByRole('button', { name: 'Linsensuppe als gegessen markieren' })).toHaveCount(
    0,
    {
      timeout: 10_000,
    },
  )
  await expect(a.getByRole('button', { name: 'Linsensuppe als gegessen markieren' })).toHaveCount(0)
  await shot(b, '5-eaten')

  // --- Drag the shared dinner below a late snack: its time follows ---
  await a.getByRole('link', { name: 'Essen eintragen' }).click()
  await a.getByLabel('Mahlzeit', { exact: true }).selectOption({ label: 'Snack' })
  await a.getByLabel('Uhrzeit').fill('21:00')
  await a.getByRole('button', { name: 'Schnell' }).click()
  await a.getByLabel('Was war es?').fill('Nüsse')
  await a.getByLabel('Energie (kcal)').fill('180')
  await a.getByRole('button', { name: 'Jetzt eintragen' }).click()
  await expect(card(a, 'Nüsse')).toBeVisible()
  expect(await entryOrder(a, ['Linsensuppe', 'Nüsse'])).toEqual(['Linsensuppe', 'Nüsse'])
  await drag(a, a.getByRole('button', { name: 'Linsensuppe verschieben' }), () =>
    a.getByText('Ans Ende des Tages'),
  )
  await expect.poll(() => entryOrder(a, ['Linsensuppe', 'Nüsse'])).toEqual(['Nüsse', 'Linsensuppe'])
  await expect(card(a, 'Linsensuppe')).toContainText('21:30')
  // Sam sees the new time of the dish they share.
  await expect(card(b, 'Linsensuppe')).toContainText('21:30', {
    timeout: 10_000,
  })
  await shot(a, '6-dragged')

  // --- A recipe's ingredients on the shopping list ---
  await b.goto('/recipes')
  await b.getByRole('button', { name: /Chili/ }).click()
  await b.getByLabel('Für wie viele Portionen?').fill('2')
  await b.getByRole('button', { name: 'Zutaten auf die Liste' }).click()
  await expect(b.getByTestId('added')).toContainText('2 Zutaten auf die Liste gesetzt.')
  await b.getByRole('link', { name: 'Zur Liste' }).click()
  await expect(b.getByRole('checkbox')).toHaveCount(2)
  await expect(a.getByRole('link', { name: 'Liste' })).toBeVisible()
  await a.getByRole('link', { name: 'Liste' }).click()
  await expect(a.getByRole('checkbox')).toHaveCount(2, { timeout: 10_000 })
  await shot(a, '7-list')
})
