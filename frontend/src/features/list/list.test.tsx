import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import i18n from '../../i18n'
import { renderApp } from '../../test/render'
import { ME, mockApi } from '../../test/server'
import type { ListItem, Op } from './model'
import { forgetOfflineList } from './sync'

const ALDI = '0192f1c4-0000-5000-8000-0000000000a1'
const STORES = [
  { id: ALDI, key: 'aldi', name: null, custom: false },
  { id: '0192f1c4-0000-5000-8000-0000000000a8', key: 'other', name: null, custom: false },
]

/** A tiny list server: applies operations like the real one (minus merging and parsing). */
function listServer(initial: Partial<ListItem>[] = []) {
  let items: ListItem[] = initial.map((i, n) => ({
    id: `0192f1c4-0000-7000-8000-00000000010${n}`,
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
    ...i,
  }))
  const sent: Op[] = []
  const list = () => ({ items, stores: STORES, server_time: '2026-10-06T10:00:00Z' })
  return {
    sent,
    items: () => items,
    routes: {
      'GET /api/list': () => list(),
      'GET /api/list/history': () => [
        { text: 'Spülmittel', item_id: null, category: 'household', store_id: ALDI, uses: 4 },
      ],
      'POST /api/list/ops': (body: unknown) => {
        const ops = (body as { ops: Op[] }).ops
        sent.push(...ops)
        for (const op of ops) {
          const f = op.fields ?? {}
          if (op.kind === 'add' && !items.some((i) => i.id === op.id))
            items = [
              ...items,
              {
                ...(items[0] ?? ({} as ListItem)),
                id: op.id,
                text: f.text ?? '',
                quantity: f.quantity ?? null,
                category: f.category ?? 'other',
                store_id: f.store_id ?? null,
                checked: false,
                checked_at: null,
                created_at: op.at,
              },
            ]
          if (op.kind === 'update')
            items = items.map((i) =>
              i.id === op.id
                ? {
                    ...i,
                    ...(f.checked != null ? { checked: f.checked, checked_at: op.at } : {}),
                    ...(f.quantity !== undefined ? { quantity: f.quantity } : {}),
                    ...(f.store_id !== undefined ? { store_id: f.store_id } : {}),
                  }
                : i,
            )
          if (op.kind === 'remove') items = items.filter((i) => i.id !== op.id)
        }
        return {
          results: ops.map((o) => ({ id: o.id, status: 'applied', code: null })),
          list: list(),
        }
      },
    },
  }
}

function setOnline(value: boolean) {
  Object.defineProperty(navigator, 'onLine', { value, configurable: true })
}

beforeEach(async () => {
  await i18n.changeLanguage('de')
  localStorage.clear()
  sessionStorage.clear()
  forgetOfflineList()
  setOnline(true)
})
afterEach(() => vi.unstubAllGlobals())

describe('shopping list', () => {
  it('adds with one field and sends the text to be split on the server', async () => {
    const server = listServer()
    mockApi({ 'GET /api/auth/me': () => ME, ...server.routes })
    renderApp('/list')
    const user = userEvent.setup()
    const field = await screen.findByLabelText('Auf die Liste')
    await user.type(field, '2 Milch{Enter}')
    expect(await screen.findByRole('checkbox', { name: '2 Milch' })).toBeInTheDocument()
    expect(server.sent[0]).toMatchObject({ kind: 'add', fields: { text: '2 Milch', parse: true } })
    expect(field).toHaveValue('')
    expect(field).toHaveFocus()
  })

  it('suggests from the household history with its aisle and store', async () => {
    const server = listServer()
    mockApi({ 'GET /api/auth/me': () => ME, ...server.routes, 'GET /api/items': () => [] })
    renderApp('/list')
    const user = userEvent.setup()
    await user.type(await screen.findByLabelText('Auf die Liste'), 'spü')
    const suggestions = await screen.findByRole('list', { name: 'Vorschläge' })
    await user.click(within(suggestions).getByRole('button', { name: /Spülmittel/ }))
    await vi.waitFor(() => expect(server.sent).toHaveLength(1))
    expect(server.sent[0]?.fields).toEqual({
      text: 'Spülmittel',
      category: 'household',
      store_id: ALDI,
      parse: false,
    })
    // Grouped under its aisle, with the store shown.
    const aisle = await screen.findByRole('region', { name: 'Haushalt' })
    expect(within(aisle).getByText('ALDI')).toBeInTheDocument()
  })

  it('checks off with undo, and checked items move to the bottom', async () => {
    const server = listServer([
      { text: 'Brot', category: 'bakery' },
      { text: 'Äpfel', category: 'produce' },
    ])
    mockApi({ 'GET /api/auth/me': () => ME, ...server.routes })
    renderApp('/list')
    const user = userEvent.setup()
    await user.click(await screen.findByRole('checkbox', { name: 'Äpfel' }))
    expect(screen.getByRole('checkbox', { name: 'Äpfel' })).toBeChecked()
    expect(await screen.findByRole('region', { name: 'Abgehakt' })).toHaveTextContent('Äpfel')
    await user.click(screen.getByRole('button', { name: 'Rückgängig' }))
    await vi.waitFor(() => expect(server.sent.map((o) => o.fields?.checked)).toEqual([true, false]))
    expect(screen.getByRole('checkbox', { name: 'Äpfel' })).not.toBeChecked()
  })

  it('keeps working offline and sends the queue when the connection returns', async () => {
    const server = listServer([{ text: 'Milch', category: 'dairy_eggs' }])
    const api = mockApi({ 'GET /api/auth/me': () => ME, ...server.routes })
    renderApp('/list')
    const user = userEvent.setup()
    await screen.findByRole('checkbox', { name: 'Milch' })

    // Airplane mode: every request fails.
    setOnline(false)
    api.fetchMock.mockImplementation(() => Promise.reject(new TypeError('Failed to fetch')))
    await user.click(screen.getByRole('checkbox', { name: 'Milch' }))
    await user.type(screen.getByLabelText('Auf die Liste'), 'Brot{Enter}')
    expect(screen.getByRole('checkbox', { name: 'Milch' })).toBeChecked()
    expect(screen.getByRole('checkbox', { name: 'Brot' })).toBeInTheDocument()
    expect(await screen.findByTestId('pending')).toHaveTextContent(
      '2 Änderungen warten auf Verbindung.',
    )
    expect(JSON.parse(localStorage.getItem('mahlzeit.outbox') ?? '{}').value).toHaveLength(2)
    expect(server.sent).toEqual([])

    // Back online: the queue goes out in order, once.
    mockApi({ 'GET /api/auth/me': () => ME, ...server.routes })
    setOnline(true)
    window.dispatchEvent(new Event('online'))
    await vi.waitFor(() => expect(server.sent.map((o) => o.kind)).toEqual(['update', 'add']))
    await vi.waitFor(() =>
      expect(JSON.parse(localStorage.getItem('mahlzeit.outbox') ?? '{}').value).toEqual([]),
    )
    expect(server.items().map((i) => [i.text, i.checked])).toEqual([
      ['Milch', true],
      ['Brot', false],
    ])
  })

  it('edits quantity and store in the item sheet', async () => {
    const server = listServer([{ text: 'Eier', category: 'dairy_eggs' }])
    mockApi({ 'GET /api/auth/me': () => ME, ...server.routes })
    renderApp('/list')
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Eier' }))
    const sheet = screen.getByRole('dialog', { name: 'Eier' })
    await user.type(within(sheet).getByLabelText('Menge'), '10')
    await user.selectOptions(within(sheet).getByLabelText('Geschäft'), ALDI)
    await user.click(within(sheet).getByRole('button', { name: 'Speichern' }))
    await vi.waitFor(() =>
      expect(server.sent[0]).toMatchObject({
        kind: 'update',
        fields: { quantity: '10', store_id: ALDI },
      }),
    )
    // The store filter appears once a store is in use.
    const filter = await screen.findByRole('group', { name: 'Geschäft' })
    expect(within(filter).getByRole('button', { name: 'ALDI' })).toBeInTheDocument()
  })

  it('opens on the list for people who chose it', async () => {
    const server = listServer()
    mockApi({
      'GET /api/auth/me': () => ({ ...ME, profile: { ...ME.profile, start_screen: 'list' } }),
      ...server.routes,
    })
    renderApp('/')
    expect(await screen.findByRole('heading', { name: 'Einkaufsliste' })).toBeInTheDocument()
  })
})
