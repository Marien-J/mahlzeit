import type { Schemas } from '../api/client'
import { todayIn } from '../lib/dates'
import { ME } from './server'

export const TODAY = () => todayIn(ME.user.time_zone)
export const PARTNER_ID = '0192f1c4-0000-7000-8000-000000000002'

type Nutrients = Schemas['NutrientsOut']

export function nutrients(values: Partial<Nutrients> = {}): Nutrients {
  return {
    kcal: null,
    protein: null,
    carbs: null,
    sugar: null,
    fat: null,
    sat_fat: null,
    fibre: null,
    salt: null,
    alcohol: null,
    ...values,
  }
}

export function totals(values: Partial<Nutrients> = {}, incomplete: string[] = []) {
  return { values: nutrients(values), incomplete }
}

export const SKYR: Schemas['ItemOut'] = {
  id: '0192f1c4-0000-7000-8000-0000000000b1',
  name: 'Skyr Natur',
  names: { de: 'Skyr Natur', en: null, nl: null },
  brand: 'Arla',
  category: 'dairy_eggs',
  base_unit: 'g',
  nutrients: nutrients({ kcal: 63, protein: 11, carbs: 4, fat: 0.2 }),
  package_size: 450,
  servings: [{ label: 'portion', amount: 150 }],
  barcodes: ['4008400401621'],
  tracking_mode: 'counted',
  source: 'custom',
  generic: false,
  favourite: true,
  image_url: null,
}

export const OATS: Schemas['ItemOut'] = {
  ...SKYR,
  id: '0192f1c4-0000-7000-8000-0000000000b2',
  name: 'Haferflocken',
  names: { de: 'Haferflocken', en: 'Rolled oats', nl: 'Havermout' },
  brand: null,
  category: 'dry_goods',
  nutrients: nutrients({ kcal: 370, protein: 13.5, carbs: 58.7, fat: 7 }),
  package_size: null,
  servings: [],
  barcodes: [],
  source: 'bls',
  generic: true,
  favourite: false,
}

export function entry(over: Partial<Schemas['EntryOut']> = {}): Schemas['EntryOut'] {
  return {
    id: '0192f1c4-0000-7000-8000-0000000000e1',
    day: TODAY(),
    slot: 'breakfast',
    at: '08:10:00',
    name: null,
    eaten_out: false,
    recipe_id: null,
    recipe_portions: null,
    joint: false,
    state: 'logged',
    share: 1,
    components: [
      {
        id: '0192f1c4-0000-7000-8000-0000000000c1',
        item_id: SKYR.id,
        name: 'Skyr Natur',
        amount: 150,
        base_unit: 'g',
        serving_label: null,
        serving_count: null,
        quick: false,
        nutrients: nutrients({ kcal: 94.5, protein: 16.5, carbs: 6, fat: 0.3 }),
      },
    ],
    participants: [
      {
        user_id: ME.user.id,
        display_name: 'Jonas',
        state: 'logged',
        share: 1,
        exact_amounts: {},
        intake: totals({ kcal: 94.5, protein: 16.5, carbs: 6, fat: 0.3 }),
      },
    ],
    intake: totals({ kcal: 94.5, protein: 16.5, carbs: 6, fat: 0.3 }),
    dish: totals({ kcal: 94.5, protein: 16.5, carbs: 6, fat: 0.3 }),
    ...over,
  }
}

export function person(over: Partial<Schemas['PersonDayOut']> = {}): Schemas['PersonDayOut'] {
  return {
    user_id: ME.user.id,
    display_name: 'Jonas',
    is_me: true,
    day_type: 'training',
    targets: { kcal: 2600, protein: 160, carbs: 300, fat: 80 },
    logged: totals({ kcal: 94.5, protein: 16.5, carbs: 6, fat: 0.3 }),
    planned: totals({ kcal: 0, protein: 0, carbs: 0, fat: 0 }),
    remaining: { kcal: 2505.5, protein: 143.5, carbs: 294, fat: 79.7 },
    projection: { kcal: 94.5, protein: 16.5, carbs: 6, fat: 0.3 },
    entries: [entry()],
    ...over,
  }
}

export function dayOf(people: Schemas['PersonDayOut'][], day = TODAY()): Schemas['DayOut'] {
  return { day, people }
}
