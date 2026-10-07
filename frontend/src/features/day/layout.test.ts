import { describe, expect, it } from 'vitest'
import { entry, person, PARTNER_ID } from '../../test/fixtures'
import { layoutDay, type Cell, type Row } from './layout'

const mk = (
  id: string,
  slot: 'breakfast' | 'lunch' | 'dinner' | 'snack',
  at: string,
  joint = false,
) => entry({ id, slot, at: `${at}:00`, joint })

const mine = (...entries: ReturnType<typeof mk>[]) => person({ entries })
const theirs = (...entries: ReturnType<typeof mk>[]) =>
  person({ user_id: PARTNER_ID, display_name: 'Sam', is_me: false, entries })

/** A compact picture of the rows: "me|them" with ids, "-slot" for a dash, "=id" for joint. */
function shape(rows: Row[]): string[] {
  const cell = (c: Cell | null) =>
    c == null ? '.' : c.kind === 'entry' ? c.entry.id : `-${c.slot[0]}`
  return rows.map((r) =>
    r.kind === 'joint' ? `=${r.mine.id}` : `${cell(r.mine)}|${cell(r.theirs)}`,
  )
}

describe('day layout', () => {
  it('puts the same meal of both people side by side and dashes for what is missing', () => {
    const rows = layoutDay(
      mine(mk('a', 'breakfast', '08:00')),
      theirs(mk('b', 'breakfast', '08:30')),
    )
    expect(shape(rows)).toEqual(['a|b', '-l|-l', '-d|-d'])
  })

  it('lets a joint meal span both columns, between the rows around it', () => {
    const rows = layoutDay(
      mine(mk('a', 'breakfast', '08:00'), mk('j', 'dinner', '19:00', true)),
      theirs(mk('b', 'breakfast', '07:45'), mk('j', 'dinner', '19:00', true)),
    )
    expect(rows.map((r) => r.kind)).toEqual(['split', 'split', 'joint'])
    expect(shape(rows)[2]).toBe('=j')
  })

  it('matches the two views of a joint meal by id', () => {
    const rows = layoutDay(
      mine(mk('j', 'dinner', '19:00', true)),
      theirs(mk('j', 'dinner', '19:00', true)),
    )
    expect(shape(rows)).toEqual(['-b|-b', '-l|-l', '=j'])
  })

  it('keeps each persons own extra meals in their column, in time order', () => {
    const rows = layoutDay(
      mine(mk('a', 'breakfast', '08:00'), mk('s', 'snack', '10:00'), mk('l', 'lunch', '12:30')),
      theirs(mk('b', 'breakfast', '08:00'), mk('m', 'lunch', '12:30')),
    )
    expect(shape(rows)).toEqual(['a|b', 's|.', 'l|m', '-d|-d'])
  })

  it('waits for the partner before a joint meal, even when they have earlier meals', () => {
    const rows = layoutDay(
      mine(mk('j', 'lunch', '12:30', true)),
      theirs(mk('x', 'snack', '10:00'), mk('j', 'lunch', '12:30', true)),
    )
    expect(shape(rows)).toEqual(['-b|-b', '.|x', '=j', '-d|-d'])
  })

  it('shows one column when nobody else is in the household', () => {
    const rows = layoutDay(mine(mk('a', 'breakfast', '08:00')), null)
    expect(shape(rows)).toEqual(['a|.', '-l|.', '-d|.'])
  })

  it('never loops on mismatched joint meals', () => {
    const rows = layoutDay(
      mine(mk('j1', 'lunch', '12:30', true), mk('j', 'dinner', '19:00', true)),
      theirs(mk('j', 'dinner', '19:00', true), mk('j1', 'lunch', '12:30', true)),
    )
    expect(rows.length).toBeGreaterThan(0)
  })
})
