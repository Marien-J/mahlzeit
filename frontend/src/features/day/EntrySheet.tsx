import { useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ErrorMessage } from '../../components/ErrorMessage'
import { SelectField, Toggle } from '../../components/Field'
import { Sheet } from '../../components/Sheet'
import { hhmm, type SlotName } from '../../lib/dates'
import { grams, kcal } from '../../lib/nutrition'
import {
  copyEntry,
  deleteEntry,
  saveAsMeal,
  setEntryState,
  updateEntry,
  useRefreshDays,
  type ComponentIn,
  type Entry,
} from './api'
import { entryTitle } from './PersonColumn'

const SLOTS: SlotName[] = ['breakfast', 'lunch', 'dinner', 'snack']

export function EntrySheet({
  entry,
  own,
  today,
  onClose,
}: {
  entry: Entry
  own: boolean
  today: string
  onClose: () => void
}) {
  const { t } = useTranslation()
  const refresh = useRefreshDays()
  const [at, setAt] = useState(hhmm(entry.at))
  const [slot, setSlot] = useState<SlotName>(entry.slot)
  const [eatenOut, setEatenOut] = useState(entry.eaten_out)
  const [amounts, setAmounts] = useState<Record<string, string>>(
    Object.fromEntries(
      entry.components.map((c) => [c.id, c.amount == null ? '' : String(c.amount)]),
    ),
  )
  const [saved, setSaved] = useState(false)
  const done = async () => {
    await refresh()
    onClose()
  }
  const components: ComponentIn[] = entry.components.map((c) =>
    c.quick
      ? {
          quick_name: c.name,
          kcal: c.nutrients.kcal,
          protein: c.nutrients.protein,
          carbs: c.nutrients.carbs,
          fat: c.nutrients.fat,
        }
      : { item_id: c.item_id, amount: Number(amounts[c.id]) },
  )
  const save = useMutation({
    mutationFn: () => updateEntry(entry.id, { at, slot, eaten_out: eatenOut, components }),
    onSuccess: done,
  })
  const eaten = useMutation({
    mutationFn: () => setEntryState(entry.id, 'logged'),
    onSuccess: done,
  })
  const remove = useMutation({ mutationFn: () => deleteEntry(entry.id), onSuccess: done })
  // Own entries repeat today; the partner's entry is copied to the same day for oneself.
  const copy = useMutation({
    mutationFn: () => copyEntry(entry.id, own ? today : entry.day),
    onSuccess: done,
  })
  const asMeal = useMutation({
    mutationFn: () => saveAsMeal(entry.id),
    onSuccess: () => setSaved(true),
  })
  const error = save.error ?? eaten.error ?? remove.error ?? copy.error ?? asMeal.error

  return (
    <Sheet title={entryTitle(entry)} onClose={onClose}>
      <div className="stack">
        {entry.state === 'planned' ? <p className="badge">{t('entry.planned')}</p> : null}
        <ul className="list compact">
          {entry.components.map((c) => (
            <li key={c.id} className="row spread">
              <span>{c.name}</span>
              {own && !c.quick ? (
                <label className="amount">
                  <input
                    type="number"
                    inputMode="decimal"
                    min={0}
                    aria-label={t('log.amountOf', { name: c.name })}
                    value={amounts[c.id] ?? ''}
                    onChange={(e) => setAmounts((a) => ({ ...a, [c.id]: e.target.value }))}
                  />
                  {c.base_unit}
                </label>
              ) : (
                <span className="muted">
                  {c.amount != null ? `${grams(c.amount)} ${c.base_unit ?? ''}` : ''}
                </span>
              )}
              <span className="kcal">{kcal(c.nutrients.kcal)}</span>
            </li>
          ))}
        </ul>
        {entry.intake ? (
          <p className="muted">
            {t('totals.kcal', { value: kcal(entry.intake.values.kcal) })} ·{' '}
            {t('macro.short.protein')} {grams(entry.intake.values.protein)}
          </p>
        ) : null}
        {own ? (
          <>
            <div className="row">
              <label className="field">
                <span>{t('log.time')}</span>
                <input type="time" value={at} onChange={(e) => setAt(e.target.value)} />
              </label>
              <SelectField
                label={t('log.slot')}
                value={slot}
                options={SLOTS.map((s) => ({ value: s, label: t(`slot.${s}`) }))}
                onChange={(v) => setSlot(v as SlotName)}
              />
            </div>
            <Toggle label={t('entry.eatenOut')} checked={eatenOut} onChange={setEatenOut} />
            <ErrorMessage error={error} />
            {saved ? <p role="status">{t('entry.savedAsMeal')}</p> : null}
            <div className="row wrap">
              {entry.state === 'planned' ? (
                <button type="button" className="primary" onClick={() => eaten.mutate()}>
                  {t('entry.eaten')}
                </button>
              ) : null}
              <button
                type="button"
                className="primary"
                onClick={() => save.mutate()}
                disabled={save.isPending}
              >
                {t('common.save')}
              </button>
              <button
                type="button"
                onClick={() => asMeal.mutate()}
                disabled={asMeal.isPending || saved}
              >
                {t('entry.saveAsMeal')}
              </button>
              {entry.day !== today ? (
                <button type="button" onClick={() => copy.mutate()}>
                  {t('entry.copyToToday')}
                </button>
              ) : null}
              <button type="button" className="danger" onClick={() => remove.mutate()}>
                {t('entry.delete')}
              </button>
            </div>
          </>
        ) : (
          <>
            <ErrorMessage error={error} />
            <button type="button" className="primary" onClick={() => copy.mutate()}>
              {t('entry.copyToMyDay')}
            </button>
          </>
        )}
      </div>
    </Sheet>
  )
}
