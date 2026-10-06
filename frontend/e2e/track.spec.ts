import { expect, test, type APIRequestContext, type Page } from '@playwright/test'

/**
 * M1 on a phone viewport: one full day logged through the UI and checked against a hand
 * calculation, a barcode scan timed from the scan tab to the logged entry, and another day
 * logged through the Claude connector (MCP over HTTP, the same calls Claude makes).
 *
 * Needs the Open Food Facts stub (scripts/e2e.sh starts the stack with it).
 */
const code = process.env.E2E_TRACK_INVITE_CODE ?? ''
const run = Date.now().toString(36)
const password = 'a long e2e password'
const NUTELLA = '4008400401621' // backend/tests/fixtures/off_product_complete.json

test.skip(!code, 'E2E_TRACK_INVITE_CODE is not set; run scripts/e2e.sh')
test.use({ locale: 'de-DE', timezoneId: 'Europe/Berlin' })

async function shot(page: Page, name: string) {
  await page.screenshot({ path: `test-results/m1-${name}.png`, fullPage: true })
}

/** Search, pick, set the amount, and either add to the basket or log right away. */
async function addFood(page: Page, query: string, name: string, grams: number, logNow = false) {
  const search = page.getByLabel('Lebensmittel suchen')
  await search.fill(query)
  await page
    .getByTestId('results')
    .getByRole('button', { name: new RegExp(name) })
    .first()
    .click()
  const amount = page.getByLabel(/^Menge/)
  await amount.fill(String(grams))
  await page
    .getByRole('button', { name: logNow ? 'Jetzt eintragen' : 'Weiteres hinzufügen' })
    .click()
}

async function startMeal(page: Page, slot: string, time: string) {
  await page.getByRole('link', { name: 'Essen eintragen' }).click()
  await page.getByLabel('Mahlzeit', { exact: true }).selectOption({ label: slot })
  await page.getByLabel('Uhrzeit').fill(time)
}

test('a full day by hand, a timed scan, and a day through the connector', async ({
  page,
  request,
}) => {
  test.setTimeout(120_000)
  // --- Jonas starts a household ---
  await page.goto('/join')
  await page.getByLabel('Einladungscode').fill(code)
  await page.getByRole('button', { name: 'Weiter' }).click()
  await page.getByLabel('Dein Name').fill('Jonas')
  await page.getByLabel('E-Mail').fill(`jonas-track-${run}@example.org`)
  await page.getByLabel('Passwort').fill(password)
  await page.getByLabel('Name des Haushalts').fill(`Track ${run}`)
  await page.getByRole('button', { name: 'Konto anlegen' }).click()
  await expect(page.getByRole('heading', { name: 'Heute' })).toBeVisible()

  // --- Targets: 2600 kcal, 160 g protein every day ---
  await page.getByRole('link', { name: 'Einstellungen' }).click()
  await page.getByRole('link', { name: 'Ziele und Tagestypen' }).click()
  await page.getByLabel('kcal', { exact: true }).fill('2600')
  await page.getByLabel('Eiweiß (g)').fill('160')
  await page.getByRole('button', { name: 'Speichern' }).click()
  await expect(page.getByText('Ziele gespeichert.')).toBeVisible()
  await page.getByRole('link', { name: 'Heute' }).click()

  // --- Breakfast: 60 g oats, 200 g milk 1.5 %, 120 g banana, logged as one meal ---
  await startMeal(page, 'Frühstück', '07:45')
  await addFood(page, 'haferflocken', 'Hafer Flocken', 60)
  await addFood(page, 'milch 1,5', 'Milch fettarm', 200)
  await addFood(page, 'banane', 'Banane roh', 120)
  await page
    .getByTestId('basket')
    .getByRole('button', { name: /3 Lebensmittel eintragen/ })
    .click()
  await expect(page.getByRole('heading', { name: 'Heute' })).toBeVisible()

  // --- Lunch: 150 g chicken breast, 80 g rice ---
  await startMeal(page, 'Mittagessen', '12:30')
  await addFood(page, 'hähnchen brustfilet', 'Hähnchen Brustfilet', 150)
  await addFood(page, 'reis poliert', 'Reis poliert', 80)
  await page
    .getByTestId('basket')
    .getByRole('button', { name: /2 Lebensmittel eintragen/ })
    .click()

  // --- Snack: scan a jar the household has never had. Timed from the scan tab. ---
  await page.getByRole('link', { name: 'Essen eintragen' }).click()
  await page.getByLabel('Mahlzeit', { exact: true }).selectOption({ label: 'Snack' })
  await page.getByLabel('Uhrzeit').fill('16:00')
  const scanStart = Date.now()
  await page.getByRole('button', { name: 'Scannen' }).click()
  await page.getByLabel('Strichcode-Nummer').fill(NUTELLA)
  await page.getByRole('button', { name: 'Nachschlagen' }).click()
  // Open Food Facts had every value: the label form only needs a confirming tap.
  const label = page.getByRole('dialog', { name: 'Nährwerttabelle' })
  await expect(label.getByLabel('Energie (kcal)')).toHaveValue('539')
  await label.getByRole('button', { name: 'Speichern' }).click()
  // The amount sheet opens on the package's serving (15 g).
  await expect(page.getByLabel(/^Menge/)).toHaveValue('15')
  await page.getByRole('button', { name: 'Jetzt eintragen' }).click()
  await expect(page.getByTestId('column-me').getByText('Nutella')).toBeVisible()
  const scanSeconds = (Date.now() - scanStart) / 1000
  console.log(`scan-to-logged (first scan, new product): ${scanSeconds.toFixed(1)} s`)
  expect(scanSeconds).toBeLessThan(20)

  // --- Dinner out: quick add with calories and protein only ---
  await startMeal(page, 'Abendessen', '19:30')
  await page.getByRole('button', { name: 'Schnell' }).click()
  await page.getByLabel('Was war es?').fill('Pizza beim Italiener')
  await page.getByLabel('Energie (kcal)').fill('850')
  await page.getByLabel('Eiweiß (g)').fill('35')
  await page.getByRole('button', { name: 'Jetzt eintragen' }).click()

  // --- Totals against the hand calculation (BLS values per 100 g) ---
  // oats 60 g × 348 = 208.8   milk 200 g × 44 = 88      banana 120 g × 79 = 94.8
  // chicken 150 g × 109 = 163.5   rice 80 g × 351 = 280.8   Nutella 15 g × 539 = 80.85
  // pizza 850                                         total 1766.75 kcal → 1.767
  // protein: 7.932 + 6.98 + 1.583 + 34.875 + 6.345 + 0.945 + 35 = 93.66 g → left 66.34 → 66
  const mine = page.getByTestId('column-me')
  await expect(mine.getByText('1.767 von 2.600 kcal')).toBeVisible()
  await expect(mine.getByTestId('remaining')).toHaveText('Noch 833 kcal und 66 g Eiweiß')
  await shot(page, '1-day-by-hand')

  // --- The same product again the next time: straight to the amount ---
  await page.getByRole('link', { name: 'Essen eintragen' }).click()
  const again = Date.now()
  await page.getByRole('button', { name: 'Scannen' }).click()
  await page.getByLabel('Strichcode-Nummer').fill(NUTELLA)
  await page.getByRole('button', { name: 'Nachschlagen' }).click()
  await page.getByRole('button', { name: 'Jetzt eintragen' }).click()
  await expect(mine.getByText('1.848 von 2.600 kcal')).toBeVisible()
  console.log(`scan-to-logged (known product): ${((Date.now() - again) / 1000).toFixed(1)} s`)

  // --- Connector: create the personal link in settings ---
  await page.getByRole('link', { name: 'Einstellungen' }).click()
  await page.getByRole('button', { name: 'Link erstellen' }).click()
  const url = await page.getByLabel('Connector-Link').inputValue()
  expect(url).toMatch(/\/mcp\/[\w-]{40,}$/)
  await shot(page, '2-connector')

  // --- Yesterday through the connector, as Claude would do it ---
  const mcp = new Mcp(request, new URL(url).pathname)
  await mcp.initialize()
  const tools = (await mcp.rpc('tools/list')) as { tools: { name: string }[] }
  expect(tools.tools.map((t) => t.name)).toEqual(
    expect.arrayContaining(['search_items', 'log_food', 'get_day']),
  )
  // Yesterday as the app sees it (the user's time zone).
  await page.getByRole('link', { name: 'Heute' }).click()
  await page.getByRole('button', { name: 'Vorheriger Tag' }).click()
  await expect(page).toHaveURL(/\/day\/\d{4}-\d{2}-\d{2}$/)
  const yesterday = new URL(page.url()).pathname.split('/').pop() ?? ''
  const find = async (query: string) => {
    const hits = (await mcp.tool('search_items', { query, limit: 1 })) as {
      items: { id: string }[]
    }
    expect(hits.items.length).toBeGreaterThan(0)
    return hits.items[0]?.id
  }
  const oats = await find('Haferflocken')
  const chicken = await find('Hähnchen Brustfilet roh')
  await mcp.tool('log_food', {
    day: yesterday,
    slot: 'breakfast',
    time: '08:00',
    foods: [{ item_id: oats, amount: 100 }],
  })
  await mcp.tool('log_food', {
    day: yesterday,
    slot: 'lunch',
    time: '13:00',
    foods: [{ item_id: chicken, amount: 200 }],
  })
  await mcp.tool('log_food', {
    day: yesterday,
    slot: 'dinner',
    time: '19:00',
    quick_add: [{ name: 'Döner', kcal: 700 }],
  })
  // 100 g oats 348 + 200 g chicken 218 + 700 = 1266 kcal
  const day = (await mcp.tool('get_day', { day: yesterday })) as {
    people: { is_me: boolean; logged: { values: { kcal: number } } }[]
  }
  expect(Math.round(day.people.find((p) => p.is_me)?.logged.values.kcal ?? 0)).toBe(1266)

  // --- …and the UI shows the same day ---
  await page.reload()
  // The targets start today, so yesterday shows the total alone.
  await expect(mine.getByText('1.266 kcal', { exact: true })).toBeVisible()
  await expect(mine.getByText('Döner')).toBeVisible()
  await shot(page, '3-day-by-connector')
})

/** A minimal MCP client over Streamable HTTP (JSON responses, stateless server). */
class Mcp {
  private id = 0
  constructor(
    private request: APIRequestContext,
    private path: string,
  ) {}

  async rpc(method: string, params: object = {}): Promise<unknown> {
    const response = await this.request.post(this.path, {
      headers: {
        Accept: 'application/json, text/event-stream',
        'Content-Type': 'application/json',
        'MCP-Protocol-Version': '2025-06-18',
      },
      data: { jsonrpc: '2.0', id: ++this.id, method, params },
    })
    expect(response.status()).toBe(200)
    const body = (await response.json()) as { result?: unknown; error?: unknown }
    expect(body.error).toBeUndefined()
    return body.result
  }

  initialize() {
    return this.rpc('initialize', {
      protocolVersion: '2025-06-18',
      capabilities: {},
      clientInfo: { name: 'mahlzeit-e2e', version: '1' },
    })
  }

  async tool(name: string, args: object): Promise<unknown> {
    const result = (await this.rpc('tools/call', { name, arguments: args })) as {
      isError?: boolean
      structuredContent?: unknown
      content: { text: string }[]
    }
    expect(result.isError ?? false, result.content[0]?.text).toBe(false)
    return result.structuredContent
  }
}
