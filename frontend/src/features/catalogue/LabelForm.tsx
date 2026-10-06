import { useMutation } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { ErrorMessage } from '../../components/ErrorMessage'
import { Field, SelectField } from '../../components/Field'
import { LABEL_FIELDS } from '../../lib/nutrition'
import { createItem, updateItem, type Item, type ItemIn } from './api'

export const CATEGORIES = [
  'produce',
  'bakery',
  'meat_fish',
  'dairy_eggs',
  'dry_goods',
  'canned',
  'frozen',
  'oils_fats',
  'spices_condiments',
  'sweets_snacks',
  'drinks',
  'household',
  'personal_care',
  'other',
] as const

const LANGS = ['de', 'en', 'nl'] as const
const UNITS = ['g', 'ml'] as const
type Lang = (typeof LANGS)[number]

export const EMPTY_ITEM: ItemIn = {
  names: {},
  category: 'other',
  base_unit: 'g',
  nutrients: {},
  servings: [],
  barcodes: [],
  tracking_mode: 'counted',
  source: 'custom',
}

function num(value: string): number | null {
  if (value.trim() === '') return null
  const n = Number(value.replace(',', '.'))
  return Number.isFinite(n) ? n : null
}

/** The label form: mirrors a German nutrition label, values per 100 g or 100 ml. */
export function LabelForm({
  initial,
  itemId,
  language,
  missing = [],
  onSaved,
}: {
  initial: ItemIn
  itemId?: string
  language: string
  missing?: string[]
  onSaved: (item: Item) => void
}) {
  const { t } = useTranslation()
  const lang = ((LANGS as readonly string[]).includes(language) ? language : 'de') as Lang
  const [names, setNames] = useState<Record<Lang, string>>({
    de: initial.names.de ?? '',
    en: initial.names.en ?? '',
    nl: initial.names.nl ?? '',
  })
  const [brand, setBrand] = useState(initial.brand ?? '')
  const [category, setCategory] = useState(initial.category ?? 'other')
  const [unit, setUnit] = useState(initial.base_unit ?? 'g')
  const [values, setValues] = useState<Record<string, string>>(
    Object.fromEntries(
      LABEL_FIELDS.map((f) => [
        f,
        initial.nutrients?.[f] == null ? '' : String(initial.nutrients[f]),
      ]),
    ),
  )
  const [packageSize, setPackageSize] = useState(
    initial.package_size ? String(initial.package_size) : '',
  )
  const [servings, setServings] = useState(
    (initial.servings ?? []).map((s) => ({ ...s, amount: String(s.amount) })),
  )
  const [barcode, setBarcode] = useState(initial.barcodes?.[0] ?? '')
  const [otherNames, setOtherNames] = useState(false)

  const save = useMutation({
    mutationFn: () => {
      const body: ItemIn = {
        ...initial,
        names: { de: names.de || null, en: names.en || null, nl: names.nl || null },
        brand: brand || null,
        category,
        base_unit: unit,
        nutrients: Object.fromEntries(LABEL_FIELDS.map((f) => [f, num(values[f] ?? '')])),
        package_size: num(packageSize),
        servings: servings
          .filter((s) => s.label.trim() && num(s.amount))
          .map((s) => ({ label: s.label.trim(), amount: num(s.amount) ?? 0 })),
        barcodes: barcode.trim() ? [barcode.trim()] : [],
      }
      return itemId ? updateItem(itemId, body) : createItem(body)
    },
    onSuccess: onSaved,
  })

  function submit(e: FormEvent) {
    e.preventDefault()
    save.mutate()
  }

  const unitLabel = unit === 'ml' ? '100 ml' : '100 g'
  return (
    <form className="stack label-form" onSubmit={submit}>
      <Field
        label={t('label.name')}
        required
        value={names[lang]}
        onChange={(e) => setNames((n) => ({ ...n, [lang]: e.target.value }))}
      />
      {otherNames ? (
        LANGS.filter((l) => l !== lang).map((l) => (
          <Field
            key={l}
            label={t('label.nameIn', { language: t(`languages.${l}`) })}
            value={names[l]}
            onChange={(e) => setNames((n) => ({ ...n, [l]: e.target.value }))}
          />
        ))
      ) : (
        <button type="button" className="link" onClick={() => setOtherNames(true)}>
          {t('label.addOtherNames')}
        </button>
      )}
      <div className="row">
        <Field label={t('label.brand')} value={brand} onChange={(e) => setBrand(e.target.value)} />
        <SelectField
          label={t('label.category')}
          value={category}
          options={CATEGORIES.map((c) => ({ value: c, label: t(`category.${c}`) }))}
          onChange={(v) => setCategory(v as ItemIn['category'])}
        />
      </div>
      <fieldset className="label-values">
        <legend>
          {t('label.per', { unit: unitLabel })}{' '}
          <select
            aria-label={t('label.unit')}
            value={unit}
            onChange={(e) => setUnit(e.target.value as 'g' | 'ml')}
          >
            {UNITS.map((u) => (
              <option key={u} value={u}>
                {t(`unit.${u}`)}
              </option>
            ))}
          </select>
        </legend>
        {LABEL_FIELDS.map((f) => (
          <label key={f} className={`label-row ${missing.includes(f) ? 'missing' : ''}`}>
            <span>{t(`nutrient.${f}`)}</span>
            <input
              inputMode="decimal"
              value={values[f]}
              aria-invalid={missing.includes(f) && !values[f] ? true : undefined}
              onChange={(e) => setValues((v) => ({ ...v, [f]: e.target.value }))}
            />
          </label>
        ))}
      </fieldset>
      <div className="row">
        <Field
          label={t('label.packageSize', { unit })}
          inputMode="decimal"
          value={packageSize}
          onChange={(e) => setPackageSize(e.target.value)}
        />
        <Field
          label={t('label.barcode')}
          inputMode="numeric"
          value={barcode}
          onChange={(e) => setBarcode(e.target.value)}
        />
      </div>
      <fieldset className="stack">
        <legend>{t('label.servings')}</legend>
        {servings.map((s, i) => (
          <div key={i} className="row">
            <Field
              label={t('label.servingName')}
              value={s.label}
              onChange={(e) =>
                setServings((all) =>
                  all.map((x, j) => (j === i ? { ...x, label: e.target.value } : x)),
                )
              }
            />
            <Field
              label={unit}
              inputMode="decimal"
              value={s.amount}
              onChange={(e) =>
                setServings((all) =>
                  all.map((x, j) => (j === i ? { ...x, amount: e.target.value } : x)),
                )
              }
            />
          </div>
        ))}
        <button
          type="button"
          onClick={() => setServings((all) => [...all, { label: '', amount: '' }])}
        >
          {t('label.addServing')}
        </button>
      </fieldset>
      <ErrorMessage error={save.error} />
      <button type="submit" className="primary" disabled={save.isPending}>
        {t('common.save')}
      </button>
    </form>
  )
}
