/** Calendar days as ISO strings (YYYY-MM-DD), always in the user's time zone. */

export function todayIn(timeZone: string, now: Date = new Date()): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone }).format(now)
}

export function nowTimeIn(timeZone: string, now: Date = new Date()): string {
  return new Intl.DateTimeFormat('en-GB', {
    timeZone,
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).format(now)
}

export function addDays(day: string, days: number): string {
  const d = new Date(`${day}T12:00:00Z`)
  d.setUTCDate(d.getUTCDate() + days)
  return d.toISOString().slice(0, 10)
}

/** A date object for formatting a calendar day without time-zone drift. */
export function dayAsDate(day: string): Date {
  return new Date(`${day}T12:00:00Z`)
}

export function hhmm(time: string): string {
  return time.slice(0, 5)
}

export type SlotName = 'breakfast' | 'lunch' | 'dinner' | 'snack'

/** The slot a person most likely means right now. */
export function slotForTime(time: string): SlotName {
  const [h = 0, m = 0] = time.split(':').map(Number)
  const minutes = h * 60 + m
  if (minutes < 10 * 60 + 30) return 'breakfast'
  if (minutes < 15 * 60) return 'lunch'
  if (minutes >= 17 * 60 + 30 && minutes < 21 * 60 + 30) return 'dinner'
  return 'snack'
}
