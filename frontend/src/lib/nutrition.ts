import { formatNumber } from '../i18n/format'

export const MACROS = ['protein', 'carbs', 'fat'] as const
export const LABEL_FIELDS = [
  'kcal',
  'protein',
  'carbs',
  'sugar',
  'fat',
  'sat_fat',
  'fibre',
  'salt',
] as const
export type LabelField = (typeof LABEL_FIELDS)[number]

export function kcal(value: number | null | undefined): string {
  return value == null ? '–' : formatNumber(Math.round(value))
}

export function grams(value: number | null | undefined, digits = 0): string {
  return value == null ? '–' : formatNumber(value, { maximumFractionDigits: digits })
}

/** Nutrients for an amount, from values per 100. */
export function scale(per100: number | null | undefined, amount: number): number | null {
  return per100 == null ? null : (per100 * amount) / 100
}

type Intake = { values: { kcal: number | null }; incomplete: string[] }

/** Energy of a meal: unknown parts show as "–" when nothing is known, else "≈". */
export function kcalOf(intake: Intake | null | undefined): string {
  if (!intake) return '–'
  const unknown = intake.incomplete.includes('kcal')
  const value = intake.values.kcal
  if (unknown && !value) return '–'
  return `${unknown ? '≈ ' : ''}${kcal(value)}`
}
