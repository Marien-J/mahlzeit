import { describe, expect, it } from 'vitest'
import { moveTarget } from './reorder'

const order = ['a', 'b', 'c', 'd']

describe('dropping a dragged entry', () => {
  it('puts it before the entry it was dropped on', () => {
    expect(moveTarget(order, 'd', 'b')).toEqual({ before: 'b' })
    expect(moveTarget(order, 'a', 'c')).toEqual({ before: 'c' })
  })

  it('puts it last when dropped below everything', () => {
    expect(moveTarget(order, 'a', null)).toEqual({ before: null })
  })

  it('does nothing when it would stay where it is', () => {
    expect(moveTarget(order, 'b', 'c')).toBeNull() // already right before c
    expect(moveTarget(order, 'd', null)).toBeNull() // already last
    expect(moveTarget(order, 'b', 'b')).toBeNull() // dropped on itself
  })

  it('ignores entries that are not in my day', () => {
    expect(moveTarget(order, 'x', 'b')).toBeNull()
    expect(moveTarget(order, 'a', 'x')).toBeNull()
  })
})
