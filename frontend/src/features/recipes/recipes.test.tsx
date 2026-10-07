import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import i18n from '../../i18n'
import { OATS, SKYR, recipe } from '../../test/fixtures'
import { renderApp } from '../../test/render'
import { ME, mockApi, reply } from '../../test/server'

beforeEach(async () => {
  await i18n.changeLanguage('de')
})
afterEach(() => vi.unstubAllGlobals())

const chili = recipe()
const curry = recipe({
  id: '0192f1c4-0000-7000-8000-0000000000f2',
  name: 'Curry',
  staple: false,
  servings: 2,
})

function routes(extra: Record<string, (body: unknown, request: Request) => unknown> = {}) {
  return {
    'GET /api/auth/me': () => ME,
    'GET /api/recipes': () => [chili, curry],
    'GET /api/items': () => [SKYR, OATS],
    ...extra,
  }
}

describe('recipes', () => {
  it('lists staples first with servings and kcal per serving', async () => {
    mockApi(routes())
    renderApp('/recipes')
    expect(await screen.findByRole('heading', { name: 'Standardrezepte' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Weitere Rezepte' })).toBeInTheDocument()
    const rows = screen.getAllByRole('button', { name: /pro Portion/ })
    expect(rows.map((r) => within(r).getByText(/^(Chili|Curry)$/).textContent)).toEqual([
      'Chili',
      'Curry',
    ])
    expect(rows[0]).toHaveTextContent('4 Portionen · 480 kcal pro Portion')
  })

  it('puts the ingredients for some portions on the list', async () => {
    const server = mockApi(
      routes({
        [`POST /api/recipes/${chili.id}/add-to-list`]: () => ({
          added: [{ id: 'x' }],
          already_listed: ['Skyr Natur'],
        }),
      }),
    )
    renderApp('/recipes')
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: /Chili/ }))
    const portions = screen.getByLabelText('Für wie viele Portionen?')
    await user.clear(portions)
    await user.type(portions, '2')
    await user.click(screen.getByRole('button', { name: 'Zutaten auf die Liste' }))
    expect(await screen.findByTestId('added')).toHaveTextContent(
      '1 Zutat auf die Liste gesetzt. Schon auf der Liste: Skyr Natur.',
    )
    const call = server.calls.find((c) => c.path.endsWith('/add-to-list'))
    expect(call?.body).toEqual({ portions: 2 })
  })

  it('creates a recipe from catalogue foods', async () => {
    const server = mockApi(routes({ 'POST /api/recipes': () => reply(201, chili) }))
    renderApp('/recipes')
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Neues Rezept' }))
    const form = screen.getByRole('dialog', { name: 'Neues Rezept' })
    await user.type(within(form).getByLabelText('Name'), 'Porridge')
    await user.clear(within(form).getByLabelText('Portionen'))
    await user.type(within(form).getByLabelText('Portionen'), '3')
    await user.click(within(form).getByRole('button', { name: 'Zutat hinzufügen' }))
    const picker = screen.getByRole('dialog', { name: 'Zutat hinzufügen' })
    await user.click(await within(picker).findByRole('button', { name: /Haferflocken/ }))
    const amount = within(form).getByLabelText('Menge von Haferflocken')
    await user.clear(amount)
    await user.type(amount, '90')
    await user.click(within(form).getByRole('switch', { name: 'Standardrezept' }))
    await user.click(within(form).getByRole('button', { name: 'Speichern' }))
    await vi.waitFor(() =>
      expect(server.calls.some((c) => c.method === 'POST' && c.path === '/api/recipes')).toBe(true),
    )
    const body = server.calls.find((c) => c.path === '/api/recipes' && c.method === 'POST')?.body
    expect(body).toEqual({
      kind: 'recipe',
      name: 'Porridge',
      servings: 3,
      cooked_yield_g: null,
      staple: true,
      notes: null,
      ingredients: [{ item_id: OATS.id, amount: 90 }],
    })
  })

  it('asks twice before deleting', async () => {
    const server = mockApi(routes({ [`DELETE /api/recipes/${curry.id}`]: () => reply(204) }))
    renderApp('/recipes')
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: /Curry/ }))
    await user.click(screen.getByRole('button', { name: 'Rezept löschen' }))
    expect(server.calls.some((c) => c.method === 'DELETE')).toBe(false)
    await user.click(screen.getByRole('button', { name: 'Wirklich löschen' }))
    await vi.waitFor(() => expect(server.calls.some((c) => c.method === 'DELETE')).toBe(true))
  })
})
