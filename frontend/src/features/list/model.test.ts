import { describe, expect, it } from 'vitest'
import { uuid7 } from '../../lib/ids'
import { normalize } from '../../lib/text'
import { applyOps, arrange, suggest, type ListItem, type Op } from './model'

const AT = '2026-10-06T10:00:00Z'

let made = 1_000_000

function item(over: Partial<ListItem>): ListItem {
  return {
    id: uuid7(made++),
    text: 'x',
    item_id: null,
    quantity: null,
    store_id: null,
    category: 'other',
    checked: false,
    checked_at: null,
    checked_by: null,
    created_by: null,
    created_at: AT,
    updated_at: AT,
    ...over,
  }
}

describe('ids and text', () => {
  it('makes time-ordered UUIDv7 ids', () => {
    const a = uuid7(1_000)
    const b = uuid7(2_000)
    expect(a).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/)
    expect(a < b).toBe(true)
    const sameMs = Array.from({ length: 50 }, () => uuid7(3_000))
    expect([...sameMs].sort()).toEqual(sameMs)
  })

  it('normalizes like the server', () => {
    expect(normalize('  Spülmittel, Großpackung! ')).toBe('spulmittel grosspackung')
  })
})

describe('the optimistic list', () => {
  it('lays queued changes over the server list', () => {
    const milk = item({ text: 'Milch' })
    const bread = item({ text: 'Brot' })
    const added = uuid7()
    const ops: Op[] = [
      { kind: 'update', id: milk.id, at: AT, fields: { checked: true, quantity: '2' } },
      { kind: 'remove', id: bread.id, at: AT },
      { kind: 'add', id: added, at: AT, fields: { text: 'Eier', category: 'dairy_eggs' } },
      { kind: 'update', id: 'gone', at: AT, fields: { checked: true } },
    ]
    const shown = applyOps([milk, bread], ops)
    expect(shown.map((i) => [i.text, i.checked, i.quantity, i.pending ?? false])).toEqual([
      ['Milch', true, '2', true],
      ['Eier', false, null, true],
    ])
  })

  it('does not add twice when the server already has the item', () => {
    const milk = item({ text: 'Milch' })
    const shown = applyOps(
      [milk],
      [{ kind: 'add', id: milk.id, at: AT, fields: { text: 'Milch' } }],
    )
    expect(shown).toHaveLength(1)
  })

  it('groups open items by aisle and puts checked ones apart', () => {
    const aldi = 'store-aldi'
    const items = [
      item({ text: 'Milch', category: 'dairy_eggs' }),
      item({ text: 'Äpfel', category: 'produce', store_id: aldi }),
      item({ text: 'Bananen', category: 'produce', store_id: 'store-lidl' }),
      item({ text: 'Brot', category: 'bakery', checked: true, checked_at: AT }),
    ]
    const all = arrange(items, null)
    expect(all.aisles.map((a) => [a.category, a.items.map((i) => i.text)])).toEqual([
      ['produce', ['Äpfel', 'Bananen']],
      ['dairy_eggs', ['Milch']],
    ])
    expect(all.done.map((i) => i.text)).toEqual(['Brot'])
    const atAldi = arrange(items, aldi)
    expect(atAldi.aisles.flatMap((a) => a.items.map((i) => i.text))).toEqual(['Äpfel', 'Milch'])
  })
})

describe('suggestions', () => {
  const history = [
    { text: 'Milch', item_id: null, category: 'dairy_eggs', store_id: null, uses: 9 },
    { text: 'Hafermilch', item_id: null, category: 'drinks', store_id: null, uses: 3 },
    { text: 'Mehl', item_id: null, category: 'dry_goods', store_id: null, uses: 1 },
  ]

  it('puts the household history first, word starts before substrings', () => {
    const hits = suggest('milch', history, [
      { id: 'c1', name: 'Milch fettarm', category: 'dairy_eggs' },
      { id: 'c2', name: 'Milch', category: 'dairy_eggs' },
    ])
    expect(hits.map((h) => [h.text, h.fromHistory])).toEqual([
      ['Milch', true],
      ['Hafermilch', true],
      ['Milch fettarm', false],
    ])
  })

  it('suggests nothing for an empty field', () => {
    expect(suggest('  ', history, [])).toEqual([])
  })
})
