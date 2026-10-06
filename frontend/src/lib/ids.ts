/**
 * UUIDv7 made on the device, so an item created offline keeps its id when it reaches the
 * server. Ids from one device always increase (a counter covers ids made in the same
 * millisecond), so they also keep the order things were added in.
 */
let lastMs = 0
let counter = 0

export function uuid7(now: number = Date.now()): string {
  const bytes = new Uint8Array(16)
  crypto.getRandomValues(bytes)
  if (now <= lastMs) {
    counter += 1
    if (counter > 0xfff) {
      lastMs += 1
      counter = 0
    }
  } else {
    lastMs = now
    counter = 0
  }
  let ms = lastMs
  for (let i = 5; i >= 0; i--) {
    bytes[i] = ms % 256
    ms = Math.floor(ms / 256)
  }
  // 12-bit counter in rand_a keeps ids from the same millisecond in order.
  bytes[6] = 0x70 | (counter >> 8)
  bytes[7] = counter & 0xff
  bytes[8] = 0x80 | ((bytes[8] ?? 0) & 0x3f)
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}
