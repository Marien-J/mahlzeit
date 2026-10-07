import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import i18n from '../../i18n'
import { addDays } from '../../lib/dates'
import { ME, mockApi, reply } from '../../test/server'
import { PARTNER_ID, TODAY, entry, nutrients, recipe, totals } from '../../test/fixtures'
import { renderApp } from '../../test/render'
import type { Schemas } from '../../api/client'

beforeEach(async () => {
  await i18n.changeLanguage('de')
})
afterEach(() => vi.unstubAllGlobals())

const planned = (name: string, over: Partial<Schemas['EntryOut']> = {}) =>
  entry({
    name,
    slot: 'dinner',
    at: '19:00:00',
    state: null,
    share: null,
    intake: null,
    dish: totals({ kcal: 1000, protein: 80 }),
    participants: [
      {
        user_id: ME.user.id,
        display_name: 'Jonas',
        state: 'planned',
        share: 0.5,
        exact_amounts: {},
        intake: totals({ kcal: 500 }),
      },
      {
        user_id: PARTNER_ID,
        display_name: 'Sam',
        state: 'planned',
        share: 0.5,
        exact_amounts: {},
        intake: totals({ kcal: 500 }),
      },
    ],
    ...over,
  })

const household = {
  id: ME.household.id,
  name: ME.household.name,
  max_members: 4,
  members: [
    { id: ME.user.id, display_name: 'Jonas' },
    { id: PARTNER_ID, display_name: 'Sam' },
  ],
}

describe('plan page', () => {
  it('shows the coming days with who eats what and a shortcut to plan more', async () => {
    const tomorrow = addDays(TODAY(), 1)
    const days = Array.from({ length: 14 }, (_, i) => ({
      day: addDays(TODAY(), i),
      entries: i === 1 ? [planned('Chili')] : [],
    }))
    const server = mockApi({
      'GET /api/auth/me': () => ME,
      'GET /api/plan': () => ({ members: [], days, offers: [] }),
    })
    renderApp('/plan')
    const day = await screen.findByTestId(`plan-${tomorrow}`)
    expect(within(day).getByRole('link', { name: 'Morgen' })).toBeInTheDocument()
    expect(within(day).getByText('Chili')).toBeInTheDocument()
    expect(within(day).getByText(/Abendessen · Jonas & Sam/)).toBeInTheDocument()
    expect(within(day).getByText('1.000 kcal gesamt')).toBeInTheDocument()
    expect(within(day).getByRole('link', { name: /Mahlzeit planen für Morgen/ })).toHaveAttribute(
      'href',
      `/add?day=${tomorrow}&slot=dinner&plan=1&from=plan`,
    )
    expect(server.calls.find((c) => c.path === '/api/plan')).toBeDefined()
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Weitere Tage zeigen' }))
    await vi.waitFor(() =>
      expect(server.calls.some((c) => c.path === '/api/plan' && c.body === undefined)).toBe(true),
    )
  })
})

describe('planning a meal', () => {
  const tomorrow = () => addDays(TODAY(), 1)
  function routes() {
    return {
      'GET /api/auth/me': () => ME,
      'GET /api/household': () => household,
      'GET /api/recipes': () => [
        recipe({ cooked_yield_g: 1200 }),
        recipe({ id: '0192f1c4-0000-7000-8000-0000000000f2', name: 'Curry', staple: false }),
      ],
      'GET /api/plan': () => ({ members: [], days: [], offers: [] }),
      'POST /api/entries': () => reply(201, planned('Chili')),
    }
  }
  const posted = (server: ReturnType<typeof mockApi>) =>
    server.calls.find((c) => c.method === 'POST' && c.path === '/api/entries')?.body

  it('plans a staple recipe for both of us and returns to the plan', async () => {
    const server = mockApi(routes())
    const { router } = renderApp(`/add?day=${tomorrow()}&slot=dinner&plan=1&from=plan`)
    const user = userEvent.setup()
    expect(await screen.findByRole('heading', { name: 'Mahlzeit planen' })).toBeInTheDocument()
    expect(screen.queryByText('Auswärts gegessen')).toBeNull()
    await user.click(await screen.findByRole('switch', { name: 'Gemeinsam essen' }))
    await user.click(await screen.findByRole('button', { name: /Chili/ }))
    // Both of us eating one dish: two portions by default.
    const form = screen.getByRole('dialog', { name: 'Chili' })
    expect(within(form).getByLabelText('Portionen')).toHaveValue('2')
    await user.click(within(form).getByRole('button', { name: 'Planen' }))
    await vi.waitFor(() => expect(router.state.location.pathname).toBe('/plan'))
    expect(posted(server)).toMatchObject({
      day: tomorrow(),
      slot: 'dinner',
      plan: true,
      joint: true,
      recipe_id: recipe().id,
      portions: 2,
    })
  })

  it('logs a portion by cooked weight', async () => {
    const server = mockApi(routes())
    renderApp(`/add?day=${tomorrow()}&slot=dinner&plan=1`)
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: /Chili/ }))
    const form = screen.getByRole('dialog', { name: 'Chili' })
    await user.type(within(form).getByLabelText('Oder: Gewicht auf dem Teller (g)'), '450')
    expect(within(form).getByLabelText('Portionen')).toBeDisabled()
    await user.click(within(form).getByRole('button', { name: 'Planen' }))
    await vi.waitFor(() => expect(posted(server)).toBeDefined())
    expect(posted(server)).toMatchObject({ cooked_grams: 450, plan: true, joint: false })
  })

  it('plans just a name', async () => {
    const server = mockApi(routes())
    renderApp(`/add?day=${tomorrow()}&slot=dinner&plan=1`)
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Schnell' }))
    await user.type(screen.getByLabelText('Was war es?'), 'Pizza vom Blech')
    expect(screen.getByText('Beim Planen reicht der Name.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Planen' }))
    await vi.waitFor(() => expect(posted(server)).toBeDefined())
    expect(posted(server)).toMatchObject({
      plan: true,
      components: [{ quick_name: 'Pizza vom Blech', kcal: null }],
    })
  })

  it('offers no sharing switch when nobody else is in the household', async () => {
    mockApi({
      ...routes(),
      'GET /api/household': () => ({ ...household, members: [household.members[0]] }),
    })
    renderApp(`/add?day=${tomorrow()}&slot=dinner&plan=1`)
    await screen.findByRole('button', { name: /Chili/ })
    expect(screen.queryByRole('switch', { name: 'Gemeinsam essen' })).toBeNull()
  })
})

void nutrients
