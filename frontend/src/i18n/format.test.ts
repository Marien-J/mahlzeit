import { afterEach, describe, expect, it } from 'vitest'
import i18n from './index'
import { formatDate, formatNumber } from './format'

afterEach(async () => {
  await i18n.changeLanguage('de')
})

describe('formatting follows the user language', () => {
  const day = new Date('2026-10-06T12:00:00Z')

  it('formats dates', async () => {
    await i18n.changeLanguage('de')
    expect(formatDate(day, { timeZone: 'UTC' })).toBe('06.10.2026')
    await i18n.changeLanguage('nl')
    expect(formatDate(day, { timeZone: 'UTC' })).toBe('6 okt 2026')
    await i18n.changeLanguage('en')
    expect(formatDate(day, { timeZone: 'UTC' })).toBe('Oct 6, 2026')
  })

  it('formats numbers', async () => {
    await i18n.changeLanguage('de')
    expect(formatNumber(1234.5)).toBe('1.234,5')
    await i18n.changeLanguage('en')
    expect(formatNumber(1234.5)).toBe('1,234.5')
  })
})
