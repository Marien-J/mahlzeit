import type { Schemas } from '../../api/client'
import { normalize } from '../../lib/text'
import { CATEGORIES } from '../catalogue/LabelForm'

export type ListItem = Schemas['ListItemOut'] & { pending?: boolean }
export type Store = Schemas['StoreOut']
export type Memory = Schemas['ListMemoryOut']
export type ListFields = Schemas['ListFieldsIn']
export type Op = Schemas['ListOpIn'] & { at: string }

/**
 * What the phone shows: the server's list with the changes still waiting in the outbox laid
 * over it, so checking off and adding feel instant online and keep working offline.
 */
export function applyOps(items: ListItem[], ops: Op[]): ListItem[] {
  let result = items.slice()
  for (const op of ops) {
    const index = result.findIndex((i) => i.id === op.id)
    const fields = op.fields ?? {}
    if (op.kind === 'remove') {
      result = result.filter((i) => i.id !== op.id)
    } else if (op.kind === 'add' && index === -1) {
      result.push({
        id: op.id,
        text: fields.text ?? '',
        item_id: fields.item_id ?? null,
        quantity: fields.quantity ?? null,
        store_id: fields.store_id ?? null,
        category: fields.category ?? 'other',
        checked: fields.checked ?? false,
        checked_at: null,
        checked_by: null,
        created_by: null,
        created_at: op.at,
        updated_at: op.at,
        pending: true,
      })
    } else if (op.kind === 'update' && index !== -1) {
      const current = result[index] as ListItem
      const next: ListItem = { ...current, pending: true }
      if (fields.text !== undefined && fields.text !== null) next.text = fields.text
      if (fields.quantity !== undefined) next.quantity = fields.quantity ?? null
      if (fields.store_id !== undefined) next.store_id = fields.store_id ?? null
      if (fields.category !== undefined && fields.category !== null) next.category = fields.category
      if (fields.checked !== undefined && fields.checked !== null) {
        next.checked = fields.checked
        next.checked_at = fields.checked ? op.at : null
      }
      result[index] = next
    }
  }
  return result
}

export type Aisle = { category: string; items: ListItem[] }

/** Open items aisle by aisle in the fixed order; checked items separately, newest first. */
export function arrange(
  items: ListItem[],
  storeId: string | null,
): { aisles: Aisle[]; done: ListItem[] } {
  const visible = storeId ? items.filter((i) => !i.store_id || i.store_id === storeId) : items
  const order = (c: string) => {
    const i = (CATEGORIES as readonly string[]).indexOf(c)
    return i === -1 ? CATEGORIES.length : i
  }
  const open = visible
    .filter((i) => !i.checked)
    .sort(
      (a, b) =>
        order(a.category) - order(b.category) ||
        a.created_at.localeCompare(b.created_at) ||
        a.id.localeCompare(b.id),
    )
  const aisles: Aisle[] = []
  for (const item of open) {
    const last = aisles[aisles.length - 1]
    if (last && last.category === item.category) last.items.push(item)
    else aisles.push({ category: item.category, items: [item] })
  }
  const done = visible
    .filter((i) => i.checked)
    .sort((a, b) => (b.checked_at ?? '').localeCompare(a.checked_at ?? ''))
  return { aisles, done }
}

export type Suggestion = {
  key: string
  text: string
  item_id: string | null
  category: string | null
  store_id: string | null
  fromHistory: boolean
}

/** Household history first (word starts before substrings), then catalogue hits not already shown. */
export function suggest(
  query: string,
  history: Memory[],
  catalogue: { id: string; name: string; category: string }[],
  limit = 6,
): Suggestion[] {
  const q = normalize(query)
  if (!q) return []
  const scored = history
    .map((m) => {
      const t = normalize(m.text)
      const rank = t.startsWith(q)
        ? 0
        : t.split(' ').some((w) => w.startsWith(q))
          ? 1
          : t.includes(q)
            ? 2
            : 3
      return { m, rank }
    })
    .filter((s) => s.rank < 3)
    .sort((a, b) => a.rank - b.rank || b.m.uses - a.m.uses)
  const result: Suggestion[] = scored.map(({ m }) => ({
    key: `h:${m.item_id ?? normalize(m.text)}`,
    text: m.text,
    item_id: m.item_id,
    category: m.category,
    store_id: m.store_id,
    fromHistory: true,
  }))
  const known = new Set(result.map((s) => s.item_id).filter(Boolean))
  const knownText = new Set(result.map((s) => normalize(s.text)))
  for (const item of catalogue) {
    if (known.has(item.id) || knownText.has(normalize(item.name))) continue
    result.push({
      key: `c:${item.id}`,
      text: item.name,
      item_id: item.id,
      category: item.category,
      store_id: null,
      fromHistory: false,
    })
  }
  return result.slice(0, limit)
}

/** Brand names are not translated; 'other' and custom stores are handled by the caller. */
export const STORE_BRANDS: Record<string, string> = {
  aldi: 'ALDI',
  lidl: 'Lidl',
  edeka: 'EDEKA',
  rewe: 'REWE',
  netto: 'Netto',
  penny: 'Penny',
  dm: 'dm',
}
