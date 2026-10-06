import i18n from './index'

/** Dates and numbers follow the user's language, not the browser's. */
export function formatDate(value: Date | string, options: Intl.DateTimeFormatOptions = {}): string {
  const date = typeof value === 'string' ? new Date(value) : value
  return new Intl.DateTimeFormat(i18n.language, { dateStyle: 'medium', ...options }).format(date)
}

export function formatDateTime(value: Date | string): string {
  return formatDate(value, { dateStyle: 'medium', timeStyle: 'short' })
}

export function formatNumber(value: number, options: Intl.NumberFormatOptions = {}): string {
  return new Intl.NumberFormat(i18n.language, options).format(value)
}

export function timeZones(): string[] {
  const zones =
    typeof Intl.supportedValuesOf === 'function' ? Intl.supportedValuesOf('timeZone') : []
  return zones.includes('UTC') ? zones : [...zones, 'UTC']
}

export function browserTimeZone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || 'Europe/Berlin'
}
