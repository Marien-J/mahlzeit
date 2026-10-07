import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import i18n from '../../i18n'
import { OATS, SKYR, TODAY, dayOf, entry, person, totals } from '../../test/fixtures'
import { renderApp } from '../../test/render'
import { ME, mockApi, reply } from '../../test/server'

beforeEach(async () => {
  await i18n.changeLanguage('de')
})
afterEach(() => vi.unstubAllGlobals())

function routes(extra: Record<string, (body: unknown, request: Request) => unknown> = {}) {
  return {
    'GET /api/auth/me': () => ME,
    [`GET /api/days/${TODAY()}`]: () => dayOf([person()]),
    'GET /api/items': (_: unknown, request: Request) => {
      const q = new URL(request.url).searchParams.get('q') ?? ''
      if (!q) return [SKYR]
      return [SKYR, OATS].filter((i) => i.name.toLowerCase().includes(q.toLowerCase().slice(0, 4)))
    },
    'POST /api/entries': () => reply(201, entry()),
    ...extra,
  }
}

const posted = (server: ReturnType<typeof mockApi>) =>
  server.calls.find((c) => c.method === 'POST' && c.path === '/api/entries')?.body as
    Record<string, unknown> | undefined

describe('adding food', () => {
  it('searches, picks a serving and logs in one tap', async () => {
    const server = mockApi(routes())
    const { router } = renderApp('/add?slot=breakfast')
    const user = userEvent.setup()
    // Favourites show before typing.
    expect(await screen.findByRole('button', { name: /Skyr Natur/ })).toBeInTheDocument()
    await user.type(screen.getByLabelText('Lebensmittel suchen'), 'hafer')
    await user.click(await screen.findByRole('button', { name: /Haferflocken/ }))
    const amount = screen.getByLabelText('Menge (g)')
    await user.clear(amount)
    await user.type(amount, '60')
    expect(screen.getByText('222 kcal')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Jetzt eintragen' }))
    await vi.waitFor(() => expect(router.state.location.pathname).toBe('/'))
    expect(posted(server)).toMatchObject({
      day: TODAY(),
      slot: 'breakfast',
      at: '08:00',
      components: [{ item_id: OATS.id, amount: 60 }],
    })
  })

  it('collects several foods into one meal', async () => {
    const server = mockApi(routes())
    renderApp('/add?slot=breakfast')
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: /Skyr Natur/ }))
    await user.click(screen.getByRole('button', { name: '1 Portion (150 g)' }))
    await user.click(screen.getByRole('button', { name: 'Weiteres hinzufügen' }))
    await user.type(screen.getByLabelText('Lebensmittel suchen'), 'hafer')
    await user.click(await screen.findByRole('button', { name: /Haferflocken/ }))
    await user.click(screen.getByRole('button', { name: 'Weiteres hinzufügen' }))
    const basket = screen.getByTestId('basket')
    expect(within(basket).getAllByRole('listitem')).toHaveLength(2)
    // 150 g skyr (95 kcal) + 100 g oats (370 kcal)
    await user.click(
      within(basket).getByRole('button', { name: '2 Lebensmittel eintragen · 465 kcal' }),
    )
    await vi.waitFor(() => expect(posted(server)).toBeDefined())
    expect(posted(server)?.components).toEqual([
      { item_id: SKYR.id, amount: 150 },
      { item_id: OATS.id, amount: 100 },
    ])
  })

  it('logs a quick add with only calories', async () => {
    const server = mockApi(routes())
    renderApp('/add?slot=snack')
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Schnell' }))
    await user.type(screen.getByLabelText('Was war es?'), 'Kuchen beim Bäcker')
    await user.type(screen.getByLabelText('Energie (kcal)'), '420')
    await user.click(screen.getByRole('button', { name: 'Jetzt eintragen' }))
    await vi.waitFor(() => expect(posted(server)).toBeDefined())
    expect(posted(server)?.components).toEqual([
      { quick_name: 'Kuchen beim Bäcker', kcal: 420, protein: null, carbs: null, fat: null },
    ])
  })

  it('logs a saved meal with one tap', async () => {
    const meal = {
      id: '0192f1c4-0000-7000-8000-0000000000f1',
      name: 'Porridge',
      ingredients: [],
      per_serving: totals({ kcal: 480 }),
    }
    const server = mockApi(routes({ 'GET /api/recipes': () => [meal] }))
    renderApp('/add?slot=breakfast')
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Mahlzeiten' }))
    await user.click(await screen.findByRole('button', { name: /Porridge/ }))
    await vi.waitFor(() => expect(posted(server)).toBeDefined())
    expect(posted(server)).toMatchObject({ recipe_id: meal.id, slot: 'breakfast' })
  })

  it('scans by typing the code when there is no camera', async () => {
    const server = mockApi(
      routes({
        [`GET /api/barcodes/${SKYR.barcodes[0]}`]: () => ({
          status: 'item',
          item: SKYR,
          draft: null,
        }),
      }),
    )
    renderApp('/add?slot=breakfast')
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Scannen' }))
    expect(await screen.findByText(/Keine Kamera verfügbar/)).toBeInTheDocument()
    await user.type(screen.getByLabelText('Strichcode-Nummer'), SKYR.barcodes[0] ?? '')
    await user.click(screen.getByRole('button', { name: 'Nachschlagen' }))
    await user.click(await screen.findByRole('button', { name: 'Jetzt eintragen' }))
    await vi.waitFor(() => expect(posted(server)).toBeDefined())
    expect(posted(server)?.components).toEqual([{ item_id: SKYR.id, amount: 150 }])
  })

  it('asks for the label when a barcode is unknown', async () => {
    mockApi(
      routes({
        'GET /api/barcodes/4000000000000': () => ({
          status: 'not_found',
          item: null,
          draft: null,
        }),
      }),
    )
    renderApp('/add?mode=scan')
    const user = userEvent.setup()
    await user.type(await screen.findByLabelText('Strichcode-Nummer'), '4000000000000')
    await user.click(screen.getByRole('button', { name: 'Nachschlagen' }))
    const sheet = await screen.findByRole('dialog', { name: 'Nährwerttabelle' })
    expect(within(sheet).getByLabelText('Strichcode')).toHaveValue('4000000000000')
    expect(within(sheet).getByLabelText('Energie (kcal)')).toHaveValue('')
  })
})
