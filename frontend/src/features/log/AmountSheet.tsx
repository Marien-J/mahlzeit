import { useState } from 'react'
import type { TFunction } from 'i18next'
import { useTranslation } from 'react-i18next'
import { Sheet } from '../../components/Sheet'
import { formatNumber } from '../../i18n/format'
import { grams, kcal, scale } from '../../lib/nutrition'
import type { Item } from '../catalogue/api'
import type { ComponentIn } from '../day/api'

export type Picked = { component: ComponentIn; label: string; kcal: number | null }

export function servingLabel(t: TFunction, label: string): string {
  return t(`serving.${label}`, { defaultValue: label })
}

/** How much of one item: serving buttons and a free amount in g or ml. */
export function AmountSheet({
  item,
  onAdd,
  onLogNow,
  onClose,
  busy,
  plan = false,
}: {
  item: Item
  onAdd: (picked: Picked) => void
  onLogNow: (picked: Picked) => void
  onClose: () => void
  busy?: boolean
  plan?: boolean
}) {
  const { t } = useTranslation()
  const first = item.servings[0]
  const [amount, setAmount] = useState(first ? String(first.amount) : '100')
  const value = Number(amount.replace(',', '.'))
  const valid = Number.isFinite(value) && value > 0
  const energy = valid ? scale(item.nutrients.kcal, value) : null
  const picked = (): Picked => ({
    component: { item_id: item.id, amount: value },
    label: `${item.name} · ${grams(value)} ${item.base_unit}`,
    kcal: energy,
  })

  return (
    <Sheet title={item.name} onClose={onClose}>
      <div className="stack">
        {item.brand ? <p className="muted">{item.brand}</p> : null}
        <p className="muted">
          {t('amount.per100', { unit: item.base_unit, kcal: kcal(item.nutrients.kcal) })} ·{' '}
          {t('macro.short.protein')} {grams(item.nutrients.protein, 1)}
        </p>
        {item.servings.length ? (
          <div className="row wrap">
            {item.servings.map((s) => (
              <button key={s.label} type="button" onClick={() => setAmount(String(s.amount))}>
                {t('amount.serving', {
                  label: servingLabel(t, s.label),
                  amount: formatNumber(s.amount),
                  unit: item.base_unit,
                })}
              </button>
            ))}
            {item.servings[0] ? (
              <button
                type="button"
                onClick={() => setAmount(String((item.servings[0]?.amount ?? 0) * 2))}
              >
                {t('amount.twice', { label: servingLabel(t, item.servings[0].label) })}
              </button>
            ) : null}
          </div>
        ) : null}
        <label className="field">
          <span>{t('amount.label', { unit: item.base_unit })}</span>
          <input
            inputMode="decimal"
            autoFocus
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            onFocus={(e) => e.target.select()}
          />
        </label>
        <p className="big">{t('totals.kcal', { value: kcal(energy) })}</p>
        <div className="row">
          <button type="button" disabled={!valid || busy} onClick={() => onAdd(picked())}>
            {t('amount.addMore')}
          </button>
          <button
            type="button"
            className="primary"
            disabled={!valid || busy}
            onClick={() => onLogNow(picked())}
          >
            {t(plan ? 'amount.planNow' : 'amount.logNow')}
          </button>
        </div>
      </div>
    </Sheet>
  )
}
