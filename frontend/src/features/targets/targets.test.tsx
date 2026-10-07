import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import i18n from '../../i18n'
import { OATS, SKYR, TODAY } from '../../test/fixtures'
import { renderApp } from '../../test/render'
import { ME, mockApi, reply } from '../../test/server'
import { current } from './TargetsPage'

beforeEach(async () => {
  await i18n.changeLanguage('de')
})
afterEach(() => vi.unstubAllGlobals())

const set = (valid_from: string, day_type: 'training' | 'rest', kcal: number) => ({
  valid_from,
  day_type,
  targets: { kcal, protein: 150, carbs: null, fat: null },
})

describe('targets', () => {
  it('picks the newest set that started on or before the day', () => {
    const history = [
      set('2026-01-01', 'training', 2500),
      set('2026-03-01', 'training', 2700),
      set('2026-02-01', 'rest', 2100),
    ]
    expect(current(history, 'training', '2026-02-15')?.targets.kcal).toBe(2500)
    expect(current(history, 'training', '2026-03-01')?.targets.kcal).toBe(2700)
    expect(current(history, 'rest', '2026-01-15')).toBeNull()
  })

  it('flips one weekday between training and rest', async () => {
    const server = mockApi({
      'GET /api/auth/me': () => ME,
      'GET /api/targets': () => ({ week_pattern: 'TRTRTRR', history: [] }),
      'PUT /api/targets/week-pattern': (body) => ({
        week_pattern: (body as { pattern: string }).pattern,
        history: [],
      }),
    })
    renderApp('/targets')
    const user = userEvent.setup()
    const week = await screen.findByRole('group', { name: 'Trainingswoche' })
    const buttons = within(week).getAllByRole('button')
    expect(buttons).toHaveLength(7)
    expect(buttons[0]).toHaveAttribute('aria-pressed', 'true')
    await user.click(buttons[1] as HTMLElement)
    await vi.waitFor(() =>
      expect(server.calls.find((c) => c.method === 'PUT')?.body).toEqual({ pattern: 'TTTRTRR' }),
    )
  })

  it('saves the same targets for both day types, or separate ones', async () => {
    const bodies: unknown[] = []
    mockApi({
      'GET /api/auth/me': () => ME,
      'GET /api/targets': () => ({
        week_pattern: 'TRTRTRR',
        history: [set('2026-01-01', 'training', 2500), set('2026-01-01', 'rest', 2500)],
      }),
      'PUT /api/targets': (body) => {
        bodies.push(body)
        return { week_pattern: 'TRTRTRR', history: [] }
      },
    })
    renderApp('/targets')
    const user = userEvent.setup()
    const kcal = await screen.findByLabelText('kcal')
    expect(kcal).toHaveValue('2500')
    await user.clear(kcal)
    await user.type(kcal, '2600')
    await user.click(screen.getByRole('button', { name: 'Speichern' }))
    expect(await screen.findByText('Ziele gespeichert.')).toBeInTheDocument()
    expect(bodies).toEqual([
      {
        kcal: 2600,
        protein: 150,
        carbs: null,
        fat: null,
        day_types: ['training', 'rest'],
        valid_from: TODAY(),
      },
    ])

    await user.click(
      screen.getByRole('switch', { name: 'Gleiche Ziele an Trainings- und Ruhetagen' }),
    )
    const rest = screen.getByRole('group', { name: 'Ruhetag' })
    const restKcal = within(rest).getByLabelText('kcal')
    await user.clear(restKcal)
    await user.type(restKcal, '2100')
    await user.click(screen.getByRole('button', { name: 'Speichern' }))
    await vi.waitFor(() => expect(bodies).toHaveLength(3))
    expect(bodies.slice(1)).toMatchObject([
      { kcal: 2600, day_types: ['training'] },
      { kcal: 2100, day_types: ['rest'] },
    ])
  })
})

describe('my foods', () => {
  it('lists only the household’s own items and edits one', async () => {
    const server = mockApi({
      'GET /api/auth/me': () => ME,
      'GET /api/items': () => [SKYR],
      'GET /api/recipes': () => [],
      [`PUT /api/items/${SKYR.id}`]: () => SKYR,
    })
    renderApp('/foods')
    const user = userEvent.setup()
    const list = await screen.findByTestId('own-items')
    await user.click(await within(list).findByRole('button', { name: /Skyr Natur/ }))
    const search = server.fetchMock.mock.calls
      .map(([request]) => new URL(request.url))
      .find((url) => url.pathname === '/api/items')
    expect(search?.searchParams.get('own')).toBe('true')
    const sheet = screen.getByRole('dialog', { name: 'Skyr Natur' })
    expect(within(sheet).getByRole('switch', { name: 'Favorit' })).toBeChecked()
    await user.click(within(sheet).getByRole('button', { name: 'Speichern' }))
    await vi.waitFor(() =>
      expect(server.calls.some((c) => c.method === 'PUT' && c.path.endsWith(SKYR.id))).toBe(true),
    )
  })

  it('renames a saved meal', async () => {
    const meal = {
      id: '0192f1c4-0000-7000-8000-0000000000f1',
      name: 'Porridge',
      ingredients: [{ item_id: OATS.id, name: 'Haferflocken', amount: 60, base_unit: 'g' }],
      per_serving: {
        values: {
          kcal: 222,
          protein: null,
          carbs: null,
          sugar: null,
          fat: null,
          sat_fat: null,
          fibre: null,
          salt: null,
          alcohol: null,
        },
        incomplete: [],
      },
    }
    const server = mockApi({
      'GET /api/auth/me': () => ME,
      'GET /api/items': () => [],
      'GET /api/recipes': () => [meal],
      [`PATCH /api/recipes/${meal.id}`]: () => ({ ...meal, name: 'Haferbrei' }),
      [`DELETE /api/recipes/${meal.id}`]: () => reply(204),
    })
    renderApp('/foods')
    const user = userEvent.setup()
    expect(await screen.findByText(/Noch keine eigenen Lebensmittel/)).toBeInTheDocument()
    await user.click(await screen.findByRole('button', { name: /Porridge/ }))
    const sheet = screen.getByRole('dialog', { name: 'Porridge' })
    const name = within(sheet).getByLabelText('Name')
    await user.clear(name)
    await user.type(name, 'Haferbrei')
    await user.click(within(sheet).getByRole('button', { name: 'Speichern' }))
    await vi.waitFor(() =>
      expect(server.calls.find((c) => c.method === 'PATCH')?.body).toEqual({ name: 'Haferbrei' }),
    )
  })
})
