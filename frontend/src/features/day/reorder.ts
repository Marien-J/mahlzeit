/**
 * Where a dragged entry goes. `order` is my day as shown (entry ids), `over` the entry it was
 * dropped on, or null for the end of the day. Returns what to send to the server, or null when
 * nothing changes (dropped on itself or in the place it already has).
 */
export function moveTarget(
  order: string[],
  dragged: string,
  over: string | null,
): { before: string | null } | null {
  const from = order.indexOf(dragged)
  if (from < 0) return null
  if (over === null) return from === order.length - 1 ? null : { before: null }
  if (over === dragged || !order.includes(over)) return null
  return order[from + 1] === over ? null : { before: over }
}
