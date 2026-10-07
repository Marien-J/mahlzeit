import { hhmm, type SlotName } from '../../lib/dates'
import type { Entry, PersonDay } from './api'

export const ANCHORS: { slot: SlotName; at: string }[] = [
  { slot: 'breakfast', at: '08:00' },
  { slot: 'lunch', at: '12:30' },
  { slot: 'dinner', at: '19:00' },
]

/** What one column shows at one place: a meal, or a dash where an anchor meal has nothing yet. */
export type Cell = { kind: 'entry'; entry: Entry } | { kind: 'empty'; slot: SlotName; at: string }

export type Row =
  | { kind: 'joint'; key: string; mine: Entry; theirs: Entry }
  | { kind: 'split'; key: string; mine: Cell | null; theirs: Cell | null }

const at = (c: Cell) => (c.kind === 'entry' ? hhmm(c.entry.at) : c.at)
const slotOf = (c: Cell) => (c.kind === 'entry' ? c.entry.slot : c.slot)
const keyOf = (c: Cell | null) => (c == null ? '.' : c.kind === 'entry' ? c.entry.id : `-${c.slot}`)
const isJoint = (c: Cell | undefined): c is Cell & { kind: 'entry' } =>
  c !== undefined && c.kind === 'entry' && c.entry.joint

/** One person's day in time order, with a dash for each anchor meal they have not got. */
function cellsFor(person: PersonDay): Cell[] {
  const cells: Cell[] = person.entries.map((entry) => ({ kind: 'entry', entry }))
  for (const anchor of ANCHORS) {
    if (!person.entries.some((e) => e.slot === anchor.slot))
      cells.push({ kind: 'empty', ...anchor })
  }
  return cells.sort((a, b) => at(a).localeCompare(at(b)))
}

/**
 * Both people's days as one list of rows, in time order. The same meal of both people sits side
 * by side; a meal they share spans both columns and waits for the partner's earlier meals, so
 * every row reads left to right as "what each of us has at this point".
 */
export function layoutDay(mine: PersonDay, theirs: PersonDay | null): Row[] {
  const a = cellsFor(mine)
  const b = theirs ? cellsFor(theirs) : []
  const rows: Row[] = []
  let i = 0
  let j = 0
  while (i < a.length || j < b.length) {
    const x = a[i]
    const y = b[j]
    if (x && y && isJoint(x) && isJoint(y) && x.entry.id === y.entry.id) {
      rows.push({ kind: 'joint', key: x.entry.id, mine: x.entry, theirs: y.entry })
      i++
      j++
    } else if (x && y && !isJoint(x) && !isJoint(y) && slotOf(x) === slotOf(y)) {
      rows.push({ kind: 'split', key: `${keyOf(x)}|${keyOf(y)}`, mine: x, theirs: y })
      i++
      j++
    } else if (x && (!y || (!isJoint(x) && (isJoint(y) || at(x) <= at(y))))) {
      rows.push({ kind: 'split', key: `${keyOf(x)}|.`, mine: x, theirs: null })
      i++
    } else if (y && (!x || isJoint(x) || at(y) < at(x) || isJoint(y))) {
      // The partner's meal goes first: it is earlier, or my next meal is joint and waits for it.
      rows.push({ kind: 'split', key: `.|${keyOf(y)}`, mine: null, theirs: y })
      j++
    } else {
      // Two different joint meals out of step: never wait forever.
      rows.push({ kind: 'split', key: `${keyOf(x ?? null)}|.`, mine: x ?? null, theirs: null })
      i++
    }
  }
  return rows
}
