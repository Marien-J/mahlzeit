import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import i18n from '../../i18n'
import { PARTNER_ID, TODAY, dayOf, entry, offer, person, recipe, totals } from '../../test/fixtures'
import { renderApp } from '../../test/render'
import { ME, mockApi, reply } from '../../test/server'

beforeEach(async () => {
  await i18n.changeLanguage('de')
})
afterEach(() => vi.unstubAllGlobals())

const partner = person({
  user_id: PARTNER_ID,
  display_name: 'Sam',
  is_me: false,
  day_type: 'rest',
  targets: null,
  remaining: null,
  projection: null,
  entries: [],
})

const incoming = offer()
const answered = (state: 'accepted' | 'declined') => offer({ state })

function routes(
  open = [incoming],
  extra: Record<string, (body: unknown, request: Request) => unknown> = {},
) {
  return {
    'GET /api/auth/me': () => ME,
    [`GET /api/days/${TODAY()}`]: () => dayOf([person({ entries: [] }), partner]),
    'GET /api/offers': () => open,
    'GET /api/recipes': () => [recipe()],
    ...extra,
  }
}

const respondBody = (server: ReturnType<typeof mockApi>) =>
  server.calls.find((c) => c.method === 'POST' && c.path.endsWith('/respond'))?.body

describe('offers on Today', () => {
  it('shows the meal, my share and what it does to my day', async () => {
    mockApi(routes())
    renderApp('/')
    const card = await screen.findByTestId('offer')
    expect(within(card).getByText('Sam bietet dir eine Mahlzeit an')).toBeInTheDocument()
    expect(within(card).getByText('Chili')).toBeInTheDocument()
    expect(within(card).getByTestId('effect')).toHaveTextContent(
      'Dein Anteil: 50 %, 220 kcal, Eiweiß 45 g. Dein Tag: noch 900 kcal übrig, danach 680 kcal.',
    )
  })

  it('has a badge on the Today tab with what waits for an answer', async () => {
    mockApi(routes())
    renderApp('/')
    expect(await screen.findByLabelText('1 Angebot wartet')).toHaveTextContent('1')
  })

  it('accepts', async () => {
    const server = mockApi(
      routes([incoming], {
        [`POST /api/offers/${incoming.id}/respond`]: () => answered('accepted'),
      }),
    )
    renderApp('/')
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Annehmen' }))
    await vi.waitFor(() => expect(respondBody(server)).toEqual({ action: 'accept' }))
  })

  it('declines', async () => {
    const server = mockApi(
      routes([incoming], {
        [`POST /api/offers/${incoming.id}/respond`]: () => answered('declined'),
      }),
    )
    renderApp('/')
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Ablehnen' }))
    await vi.waitFor(() => expect(respondBody(server)).toEqual({ action: 'decline' }))
  })

  it('counters with one of my own plans for the slot', async () => {
    const mine = entry({
      id: '0192f1c4-0000-7000-8000-0000000000e7',
      name: 'Curry',
      slot: 'dinner',
      state: 'planned',
      at: '19:00:00',
    })
    const lunch = entry({
      id: '0192f1c4-0000-7000-8000-0000000000e8',
      name: 'Suppe',
      slot: 'lunch',
      state: 'planned',
    })
    const server = mockApi(
      routes([incoming], {
        [`GET /api/days/${TODAY()}`]: () => dayOf([person({ entries: [mine, lunch] }), partner]),
        [`POST /api/offers/${incoming.id}/respond`]: () => offer({ state: 'countered' }),
      }),
    )
    renderApp('/')
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Anderes vorschlagen' }))
    const sheet = screen.getByRole('dialog', { name: 'Gegenvorschlag an Sam' })
    // Only my plans for the same slot are offered as an answer.
    expect(within(sheet).queryByRole('button', { name: /Suppe/ })).toBeNull()
    await user.click(await within(sheet).findByRole('button', { name: /Curry/ }))
    await vi.waitFor(() =>
      expect(respondBody(server)).toEqual({ action: 'counter', counter_entry_id: mine.id }),
    )
  })

  it('counters with a new meal from a recipe', async () => {
    const server = mockApi(
      routes([incoming], {
        [`POST /api/offers/${incoming.id}/respond`]: () => offer({ state: 'countered' }),
      }),
    )
    renderApp('/')
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Anderes vorschlagen' }))
    const sheet = screen.getByRole('dialog', { name: 'Gegenvorschlag an Sam' })
    await user.selectOptions(await within(sheet).findByLabelText('Rezept'), recipe().id)
    await user.click(within(sheet).getByRole('button', { name: 'Vorschlagen' }))
    await vi.waitFor(() =>
      expect(respondBody(server)).toEqual({
        action: 'counter',
        counter_meal: { name: null, recipe_id: recipe().id, portions: 2, components: [] },
      }),
    )
  })

  it('shows what I offered and lets me withdraw it', async () => {
    const mineOut = offer({
      id: '0192f1c4-0000-7000-8000-0000000000a2',
      incoming: false,
      from_user_id: ME.user.id,
      from_name: 'Jonas',
      to_user_id: PARTNER_ID,
      to_name: 'Sam',
    })
    const server = mockApi(
      routes([mineOut], {
        [`POST /api/offers/${mineOut.id}/withdraw`]: () => offer({ state: 'withdrawn' }),
      }),
    )
    renderApp('/')
    const user = userEvent.setup()
    expect(await screen.findByText('Wartet auf Sam')).toBeInTheDocument()
    expect(screen.queryByLabelText(/Angebote? warte/)).toBeNull() // nothing waits for me
    await user.click(screen.getByRole('button', { name: 'Zurückziehen' }))
    await vi.waitFor(() =>
      expect(server.calls.some((c) => c.path.endsWith('/withdraw'))).toBe(true),
    )
  })

  it('shows a counter-offer as such, and an error when it is no longer open', async () => {
    mockApi(
      routes([offer({ counter_of_id: '0192f1c4-0000-7000-8000-0000000000a9' })], {
        [`POST /api/offers/${incoming.id}/respond`]: () =>
          reply(409, { code: 'offer_not_pending', detail: { state: 'expired' } }),
      }),
    )
    renderApp('/')
    const user = userEvent.setup()
    expect(await screen.findByText('Sam schlägt etwas anderes vor')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Annehmen' }))
    expect(
      await screen.findByText('Dieses Angebot wurde schon beantwortet oder ist abgelaufen.'),
    ).toBeInTheDocument()
  })
})

void totals
