import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import i18n from '../../i18n'
import { renderApp } from '../../test/render'
import { ME, mockApi, reply } from '../../test/server'
import type { ListItem } from '../list/model'
import { forgetOfflineList } from '../list/sync'
import type { StockRow } from './api'

const ALDI = '0192f1c4-0000-5000-8000-0000000000a1'
const RICE = '0192f1c4-0000-7000-8000-0000000000c1'
const OIL = '0192f1c4-0000-7000-8000-0000000000c2'
const OATS = '0192f1c4-0000-7000-8000-0000000000c3'

function listItem(values: Partial<ListItem>): ListItem {
  return {
    id: '0192f1c4-0000-7000-8000-000000000100',
    text: 'x',
    item_id: null,
    quantity: null,
    store_id: null,
    category: 'other',
    checked: false,
    checked_at: null,
    checked_by: null,
    created_by: null,
    created_at: '2026-10-06T10:00:00Z',
    updated_at: '2026-10-06T10:00:00Z',
    ...values,
  }
}

function list(items: ListItem[]) {
  return {
    items,
    stores: [{ id: ALDI, key: 'aldi', name: null, custom: false }],
    server_time: '2026-10-06T10:00:00Z',
  }
}

function row(values: Partial<StockRow>): StockRow {
  return {
    item_id: RICE,
    name: 'Reis',
    category: 'dry_goods',
    base_unit: 'g',
    mode: 'counted',
    level: 850,
    status: null,
    step: 500,
    package_size: 500,
    last_moved: '2026-10-05',
    ...values,
  }
}

const STOCK = {
  rows: [
    row({}),
    row({ item_id: OATS, name: 'Haferflocken', level: 0, step: 100, package_size: null }),
    row({
      item_id: OIL,
      name: 'Olivenöl',
      category: 'oils_fats',
      mode: 'status',
      level: null,
      status: 'ok',
    }),
  ],
  checks: [{ category: 'oils_fats', checked_at: '2026-10-01T09:00:00Z', checked_by: null }],
}

beforeEach(async () => {
  await i18n.changeLanguage('de')
  localStorage.clear()
  sessionStorage.clear()
  forgetOfflineList()
})

describe('bought', () => {
  it('turns the checked items into one purchase with quantities and prices', async () => {
    let items = [
      listItem({ id: '0192f1c4-0000-7000-8000-000000000101', text: 'Brot', category: 'bakery' }),
      listItem({
        id: '0192f1c4-0000-7000-8000-000000000102',
        text: 'Reis',
        item_id: RICE,
        quantity: '1 kg',
        checked: true,
        store_id: ALDI,
      }),
      listItem({
        id: '0192f1c4-0000-7000-8000-000000000103',
        text: 'Kerzen',
        checked: true,
        store_id: ALDI,
      }),
    ]
    const api = mockApi({
      'GET /api/auth/me': () => ME,
      'GET /api/list': () => list(items),
      'GET /api/list/suggestions': () => ({ plan_days: 3, suggestions: [] }),
      'POST /api/purchases': (body) => {
        const lines = (body as { lines: unknown[] }).lines
        items = items.filter((i) => !i.checked)
        return reply(201, {
          id: (body as { id: string }).id,
          day: '2026-10-06',
          store_id: ALDI,
          created_by: ME.user.id,
          created_at: '2026-10-06T10:00:00Z',
          lines: lines.map((_, n) => ({ id: `l${n}` })),
          spend_cents: 249,
        })
      },
    })
    renderApp('/list')
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Gekauft' }))
    const sheet = screen.getByRole('dialog', { name: 'Gekauft' })
    expect(within(sheet).getByLabelText('Geschäft')).toHaveValue(ALDI)
    expect(within(sheet).getByLabelText('Menge von Reis')).toHaveValue('1 kg')
    await user.type(within(sheet).getByLabelText('Preis von Reis'), '2,49')
    expect(within(sheet).getByText(/Zusammen 2,49/)).toBeInTheDocument()
    await user.click(within(sheet).getByRole('button', { name: '2 Einträge bestätigen' }))

    expect(await screen.findByRole('status')).toHaveTextContent('2 Einträge gekauft')
    const sent = api.calls.find((c) => c.path === '/api/purchases')?.body as {
      id: string
      store_id: string
      lines: Record<string, unknown>[]
    }
    expect(sent.store_id).toBe(ALDI)
    const byText = (a: Record<string, unknown>, b: Record<string, unknown>) =>
      String(a.text).localeCompare(String(b.text))
    expect([...sent.lines].sort(byText)).toEqual([
      {
        list_item_id: '0192f1c4-0000-7000-8000-000000000103',
        item_id: null,
        text: 'Kerzen',
        quantity: null,
        price_cents: null,
      },
      {
        list_item_id: '0192f1c4-0000-7000-8000-000000000102',
        item_id: RICE,
        text: 'Reis',
        quantity: '1 kg',
        price_cents: 249,
      },
    ])
    await vi.waitFor(() =>
      expect(screen.queryByRole('checkbox', { name: 'Kerzen' })).not.toBeInTheDocument(),
    )
    expect(screen.getByRole('checkbox', { name: 'Brot' })).toBeInTheDocument()
  })

  it('refuses a price it cannot read', async () => {
    mockApi({
      'GET /api/auth/me': () => ME,
      'GET /api/list': () => list([listItem({ text: 'Milch', checked: true })]),
    })
    renderApp('/list')
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Gekauft' }))
    const sheet = screen.getByRole('dialog', { name: 'Gekauft' })
    await user.type(within(sheet).getByLabelText('Preis von Milch'), 'zwei')
    expect(within(sheet).getByRole('button', { name: '1 Eintrag bestätigen' })).toBeDisabled()
  })
})

describe('suggested', () => {
  it('shows what the list could use and adds only on a tap', async () => {
    const api = mockApi({
      'GET /api/auth/me': () => ME,
      'GET /api/list': () => list([listItem({ text: 'Haferflocken', item_id: OATS })]),
      'GET /api/list/suggestions': () => ({
        plan_days: 3,
        suggestions: [
          {
            item_id: RICE,
            name: 'Reis',
            category: 'dry_goods',
            base_unit: 'g',
            reason: 'planned',
            quantity: '150 g',
            amount: 150,
          },
          {
            item_id: OIL,
            name: 'Olivenöl',
            category: 'oils_fats',
            base_unit: 'ml',
            reason: 'low',
            quantity: null,
            amount: null,
          },
          {
            item_id: OATS,
            name: 'Haferflocken',
            category: 'dry_goods',
            base_unit: 'g',
            reason: 'usual',
            quantity: null,
            amount: null,
          },
        ],
      }),
      'POST /api/list/ops': () => ({ results: [], list: list([]) }),
    })
    renderApp('/list')
    const user = userEvent.setup()
    const section = await screen.findByRole('region', { name: 'Vorgeschlagen' })
    expect(section).toHaveTextContent('für geplante Mahlzeiten der nächsten 3 Tage')
    expect(section).toHaveTextContent('wird knapp')
    expect(within(section).queryByText('Haferflocken')).not.toBeInTheDocument() // on the list
    expect(api.calls.filter((c) => c.path === '/api/list/ops')).toEqual([])
    await user.click(within(section).getByRole('button', { name: 'Reis auf die Liste' }))
    await vi.waitFor(() =>
      expect(api.calls.find((c) => c.path === '/api/list/ops')?.body).toMatchObject({
        ops: [
          {
            kind: 'add',
            fields: {
              text: 'Reis',
              item_id: RICE,
              quantity: '150 g',
              category: 'dry_goods',
              parse: false,
            },
          },
        ],
      }),
    )
  })
})

describe('stock', () => {
  it('shows what is there aisle by aisle and flips a status with a tap', async () => {
    const api = mockApi({
      'GET /api/auth/me': () => ME,
      'GET /api/stock': () => STOCK,
      [`POST /api/stock/items/${OIL}/adjust`]: () => row({ ...STOCK.rows[2], status: 'low' }),
    })
    renderApp('/stock')
    const user = userEvent.setup()
    const dry = await screen.findByRole('region', { name: 'Trockenware' })
    expect(dry).toHaveTextContent('Reis850 g')
    expect(dry).toHaveTextContent('Haferflocken0 g')
    const oils = screen.getByRole('region', { name: 'Öle und Fette' })
    expect(oils).toHaveTextContent(/Geprüft am/)
    await user.click(within(oils).getByRole('button', { name: 'Olivenöl: genug' }))
    await vi.waitFor(() =>
      expect(api.calls.find((c) => c.path.endsWith('/adjust'))?.body).toEqual({ status: 'low' }),
    )
  })

  it('checks an aisle with steppers and sends only what changed', async () => {
    const api = mockApi({
      'GET /api/auth/me': () => ME,
      'GET /api/stock': () => STOCK,
      'POST /api/stock/checks': (body) => ({
        category: (body as { category: string }).category,
        checked_at: '2026-10-06T10:00:00Z',
        checked_by: ME.user.id,
      }),
    })
    renderApp('/stock')
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Trockenware prüfen' }))
    await user.click(screen.getByRole('button', { name: 'Reis weniger' }))
    expect(screen.getByLabelText('Reis in g')).toHaveValue('350')
    await user.click(screen.getByRole('button', { name: 'Haferflocken mehr' }))
    await user.click(screen.getByRole('button', { name: 'Haferflocken mehr' }))
    await user.click(screen.getByRole('button', { name: 'Haferflocken weniger' }))
    await user.click(screen.getByRole('button', { name: 'Trockenware als geprüft markieren' }))
    await vi.waitFor(() =>
      expect(api.calls.find((c) => c.path === '/api/stock/checks')?.body).toEqual({
        category: 'dry_goods',
        counts: { [RICE]: 350, [OATS]: 100 },
        statuses: {},
      }),
    )
    expect(await screen.findByRole('button', { name: 'Trockenware prüfen' })).toBeInTheDocument()
  })

  it('counts and writes off one item in its sheet', async () => {
    const api = mockApi({
      'GET /api/auth/me': () => ME,
      'GET /api/stock': () => STOCK,
      [`GET /api/stock/items/${RICE}`]: () => ({
        stock: STOCK.rows[0],
        movements: [
          {
            id: 'm1',
            amount: -150,
            reason: 'consumption',
            source: 'entry',
            source_id: null,
            day: '2026-10-05',
            created_by: null,
            created_at: '2026-10-05T18:00:00Z',
          },
          {
            id: 'm2',
            amount: 1000,
            reason: 'purchase',
            source: 'purchase',
            source_id: null,
            day: '2026-10-04',
            created_by: null,
            created_at: '2026-10-04T18:00:00Z',
          },
        ],
      }),
      [`POST /api/stock/items/${RICE}/adjust`]: () => row({ level: 600 }),
    })
    renderApp('/stock')
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Reis' }))
    const sheet = screen.getByRole('dialog', { name: 'Reis' })
    expect(within(sheet).getByText('Laut Vorrat da: 850 g')).toBeInTheDocument()
    const history = await within(sheet).findByRole('region', { name: 'Verlauf' })
    expect(history).toHaveTextContent('Gegessen−150 g')
    expect(history).toHaveTextContent('Gekauft+1 kg')
    await user.type(within(sheet).getByLabelText('Jetzt da (g)'), '600')
    await user.click(within(sheet).getByRole('button', { name: 'Speichern' }))
    await user.type(within(sheet).getByLabelText('Weggeworfen (g)'), '50')
    await user.click(within(sheet).getByRole('button', { name: 'Abbuchen' }))
    await vi.waitFor(() =>
      expect(api.calls.filter((c) => c.path.endsWith('/adjust')).map((c) => c.body)).toEqual([
        { count: 600 },
        { waste: 50 },
      ]),
    )
  })

  it('records a purchase by hand', async () => {
    const api = mockApi({
      'GET /api/auth/me': () => ME,
      'GET /api/stock': () => STOCK,
      'GET /api/list': () => list([]),
      'GET /api/items': () => [
        { id: RICE, name: 'Reis', brand: null, base_unit: 'g', nutrients: { kcal: 350 } },
      ],
      'POST /api/purchases': (body) => reply(201, { ...(body as object), lines: [] }),
    })
    renderApp('/stock')
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Einkauf erfassen' }))
    const sheet = screen.getByRole('dialog', { name: 'Einkauf erfassen' })
    await user.type(within(sheet).getByLabelText('Lebensmittel suchen'), 'reis')
    await user.click(await within(sheet).findByRole('button', { name: 'Reis' }))
    await user.type(within(sheet).getByLabelText('Menge von Reis'), '2 kg')
    await user.type(within(sheet).getByLabelText('Lebensmittel suchen'), 'Kerzen')
    await user.click(within(sheet).getByRole('button', { name: '„Kerzen“ als Text' }))
    await user.click(within(sheet).getByRole('button', { name: 'Speichern' }))
    await vi.waitFor(() =>
      expect(api.calls.find((c) => c.path === '/api/purchases')?.body).toMatchObject({
        store_id: null,
        lines: [
          { item_id: RICE, text: 'Reis', quantity: '2 kg', price_cents: null },
          { item_id: null, text: 'Kerzen', quantity: null, price_cents: null },
        ],
      }),
    )
  })
})

describe('report', () => {
  it('compares purchased and logged per item for a period', async () => {
    const api = mockApi({
      'GET /api/auth/me': () => ME,
      'GET /api/stock/report': () => ({
        start: '2026-09-07',
        end: '2026-10-06',
        spend_cents: 1243,
        rows: [
          {
            item_id: RICE,
            name: 'Reis',
            base_unit: 'g',
            purchased: 1000,
            logged: 450,
            wasted: 50,
            corrected: -50,
            shortfall: 0,
            level: 450,
            spend_cents: 199,
          },
        ],
      }),
    })
    renderApp('/stock/report')
    const user = userEvent.setup()
    const rice = await screen.findByRole('listitem', { name: 'Reis' })
    expect(rice).toHaveTextContent('Gekauft1 kg')
    expect(rice).toHaveTextContent('Gegessen450 g')
    expect(rice).toHaveTextContent('Weggeworfen50 g')
    expect(rice).toHaveTextContent('Korrigiert−50 g')
    expect(rice).toHaveTextContent('Noch da450 g')
    expect(rice).not.toHaveTextContent('Ergänzt')
    expect(screen.getByText(/Ausgegeben: 12,43/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '7 Tage' }))
    await vi.waitFor(() => {
      const last = api.calls.filter((c) => c.path === '/api/stock/report').at(-1)
      expect(last).toBeDefined()
    })
    const urls = api.fetchMock.mock.calls.map(([r]) => new URL((r as Request).url))
    const periods = urls
      .filter((u) => u.pathname === '/api/stock/report')
      .map((u) => [u.searchParams.get('start'), u.searchParams.get('end')])
    expect(periods).toHaveLength(2)
    const [start, end] = periods[1] ?? []
    expect((Date.parse(end ?? '') - Date.parse(start ?? '')) / 86_400_000).toBe(6)
  })
})
