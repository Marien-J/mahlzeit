import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import i18n from '../../i18n'
import { PARTNER_ID, TODAY, dayOf, entry, person, totals } from '../../test/fixtures'
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
  logged: totals({ kcal: 0, protein: 0, carbs: 0, fat: 0 }),
  entries: [],
})

describe('day view', () => {
  it('shows both people side by side with totals and empty anchor meals', async () => {
    mockApi({
      'GET /api/auth/me': () => ME,
      [`GET /api/days/${TODAY()}`]: () => dayOf([person(), partner]),
    })
    renderApp('/')
    expect(await screen.findByRole('heading', { name: 'Heute' })).toBeInTheDocument()
    const mine = await screen.findByTestId('column-me')
    expect(within(mine).getByText('95 von 2.600 kcal')).toBeInTheDocument()
    expect(within(mine).getByTestId('remaining')).toHaveTextContent(
      'Noch 2.506 kcal und 144 g Eiweiß',
    )
    expect(within(mine).getByText('Skyr Natur')).toBeInTheDocument()
    // Breakfast is logged; lunch and dinner show a dash with a shortcut to add.
    expect(within(mine).getByRole('link', { name: 'Zu Mittagessen hinzufügen' })).toHaveAttribute(
      'href',
      `/add?day=${TODAY()}&slot=lunch`,
    )
    const theirs = screen.getByTestId('column-partner')
    expect(within(theirs).getByRole('heading', { name: 'Sam' })).toBeInTheDocument()
    expect(within(theirs).queryByRole('link')).toBeNull()
    expect(screen.getByRole('button', { name: 'Trainingstag' })).toBeInTheDocument()
  })

  it('marks a planned meal as eaten', async () => {
    const planned = entry({ state: 'planned', slot: 'dinner', at: '19:00:00' })
    const server = mockApi({
      'GET /api/auth/me': () => ME,
      [`GET /api/days/${TODAY()}`]: () => dayOf([person({ entries: [planned] }), partner]),
      [`POST /api/entries/${planned.id}/state`]: () => planned,
    })
    renderApp('/')
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: /Skyr Natur/ }))
    expect(screen.getByText('Geplant')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Gegessen' }))
    await vi.waitFor(() =>
      expect(server.calls.find((c) => c.path.endsWith('/state'))?.body).toEqual({
        state: 'logged',
      }),
    )
  })

  it('copies the partner meal into one’s own day', async () => {
    const theirs = entry({ id: '0192f1c4-0000-7000-8000-0000000000e9' })
    const server = mockApi({
      'GET /api/auth/me': () => ME,
      [`GET /api/days/${TODAY()}`]: () =>
        dayOf([person({ entries: [] }), { ...partner, entries: [theirs] }]),
      [`POST /api/entries/${theirs.id}/copy`]: () => reply(201, theirs),
    })
    renderApp('/')
    const user = userEvent.setup()
    const column = await screen.findByTestId('column-partner')
    await user.click(within(column).getByRole('button', { name: /Skyr Natur/ }))
    await user.click(screen.getByRole('button', { name: 'In meinen Tag übernehmen' }))
    await vi.waitFor(() =>
      expect(server.calls.find((c) => c.path.endsWith('/copy'))?.body).toEqual({ day: TODAY() }),
    )
  })

  it('switches the day type for this day only', async () => {
    const server = mockApi({
      'GET /api/auth/me': () => ME,
      [`GET /api/days/${TODAY()}`]: () => dayOf([person(), partner]),
      [`PUT /api/days/${TODAY()}/day-type`]: () => dayOf([person({ day_type: 'rest' }), partner]),
    })
    renderApp('/')
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Trainingstag' }))
    await vi.waitFor(() =>
      expect(server.calls.find((c) => c.method === 'PUT')?.body).toEqual({ day_type: 'rest' }),
    )
  })

  it('moves between days', async () => {
    mockApi({
      'GET /api/auth/me': () => ME,
      [`GET /api/days/${TODAY()}`]: () => dayOf([person(), partner]),
      'GET /api/days/2026-01-01': () => dayOf([person({ entries: [] }), partner], '2026-01-01'),
    })
    const { router } = renderApp('/day/2026-01-01')
    expect(await screen.findByRole('heading', { name: /2026/ })).toBeInTheDocument()
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Heute' }))
    expect(router.state.location.pathname).toBe('/')
  })
})
