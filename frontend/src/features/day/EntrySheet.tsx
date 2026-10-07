import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ErrorMessage } from '../../components/ErrorMessage'
import { SelectField, Toggle } from '../../components/Field'
import { Sheet } from '../../components/Sheet'
import { hhmm, type SlotName } from '../../lib/dates'
import { grams, kcal, kcalOf } from '../../lib/nutrition'
import { OfferSheet } from '../offers/OfferSheet'
import {
  copyEntry,
  deleteEntry,
  saveAsMeal,
  setEntryState,
  setExactAmounts,
  setShare,
  updateEntry,
  useRefreshDays,
  type ComponentIn,
  type Entry,
} from './api'
import { entryTitle, isOwn } from './EntryCard'

const SLOTS: SlotName[] = ['breakfast', 'lunch', 'dinner', 'snack']
const PRESETS = [0.25, 0.5, 0.75]
const number = (text: string) => Number(text.replace(',', '.'))

export function EntrySheet({
  entry,
  me,
  partner,
  today,
  onClose,
}: {
  entry: Entry
  me: string
  partner: { id: string; name: string } | null
  today: string
  onClose: () => void
}) {
  const { t } = useTranslation()
  const refresh = useRefreshDays()
  const mine = entry.participants.find((p) => p.user_id === me)
  const own = isOwn(entry, me)
  const [at, setAt] = useState(hhmm(entry.at))
  const [slot, setSlot] = useState<SlotName>(entry.slot)
  const [eatenOut, setEatenOut] = useState(entry.eaten_out)
  const [amounts, setAmounts] = useState<Record<string, string>>(
    Object.fromEntries(
      entry.components.map((c) => [c.id, c.amount == null ? '' : String(c.amount)]),
    ),
  )
  // What I weighed out for myself of a shared dish; empty goes by my share.
  const [weighed, setWeighed] = useState<Record<string, string>>(
    Object.fromEntries(
      entry.components.map((c) => [c.id, String(mine?.exact_amounts[c.id] ?? '')]),
    ),
  )
  const [share, setShareValue] = useState(Math.round((mine?.share ?? 0.5) * 100))
  // Energy of a food without a catalogue item, e.g. a plan that was just a name.
  const [energy, setEnergy] = useState<Record<string, string>>(
    Object.fromEntries(
      entry.components
        .filter((c) => c.quick)
        .map((c) => [c.id, c.nutrients.kcal == null ? '' : String(c.nutrients.kcal)]),
    ),
  )
  const [saved, setSaved] = useState(false)
  const [offering, setOffering] = useState(false)
  const done = async () => {
    await refresh()
    onClose()
  }
  const components: ComponentIn[] = entry.components.map((c) =>
    c.quick
      ? {
          quick_name: c.name,
          kcal: (energy[c.id] ?? '').trim() === '' ? null : number(energy[c.id] ?? ''),
          protein: c.nutrients.protein,
          carbs: c.nutrients.carbs,
          fat: c.nutrients.fat,
        }
      : { item_id: c.item_id, amount: number(amounts[c.id] ?? '') },
  )
  const myShare = Math.round((mine?.share ?? 0.5) * 100)
  const save = useMutation({
    // Only what was changed here is sent, so a change the partner made meanwhile to another
    // field of a shared meal is not written over.
    mutationFn: async () => {
      const patch: Parameters<typeof updateEntry>[1] = {}
      if (at !== hhmm(entry.at)) patch.at = at
      if (slot !== entry.slot) patch.slot = slot
      if (eatenOut !== entry.eaten_out) patch.eaten_out = eatenOut
      const foodsChanged = entry.components.some((c) =>
        c.quick
          ? (energy[c.id] ?? '') !== (c.nutrients.kcal == null ? '' : String(c.nutrients.kcal))
          : (amounts[c.id] ?? '') !== (c.amount == null ? '' : String(c.amount)),
      )
      if (foodsChanged) patch.components = components
      if (Object.keys(patch).length) await updateEntry(entry.id, patch)
      if (entry.joint && share !== myShare) await setShare(entry.id, share / 100)
      const changes: Record<string, number | null> = {}
      for (const c of entry.components) {
        const was = mine?.exact_amounts[c.id]
        const text = (weighed[c.id] ?? '').trim()
        const now = text === '' ? null : number(text)
        if (c.quick || (was ?? null) === now) continue
        changes[c.id] = now
      }
      if (Object.keys(changes).length) await setExactAmounts(entry.id, changes)
    },
    onSuccess: done,
  })
  const newShare = useMutation({
    mutationFn: (percent: number) => setShare(entry.id, percent / 100),
    onSuccess: refresh,
  })
  const eaten = useMutation({
    mutationFn: () => setEntryState(entry.id, 'logged'),
    onSuccess: done,
  })
  // A tap on Eaten by mistake is undone here: my part goes back to planned.
  const notEaten = useMutation({
    mutationFn: () => setEntryState(entry.id, 'planned'),
    onSuccess: done,
  })
  const client = useQueryClient()
  const remove = useMutation({ mutationFn: () => deleteEntry(entry.id), onSuccess: done })
  // Own entries repeat today; the partner's entry is copied to the same day for oneself.
  const copy = useMutation({
    mutationFn: () => copyEntry(entry.id, own ? today : entry.day),
    onSuccess: done,
  })
  const asMeal = useMutation({
    mutationFn: () => saveAsMeal(entry.id),
    onSuccess: () => {
      setSaved(true)
      void client.invalidateQueries({ queryKey: ['recipes'] })
    },
  })
  const error =
    save.error ??
    newShare.error ??
    eaten.error ??
    notEaten.error ??
    remove.error ??
    copy.error ??
    asMeal.error
  // In a column the entry carries that person's state; in the plan, mine is in the participants.
  const state = entry.state ?? mine?.state
  const canOffer =
    own && partner !== null && !entry.joint && state === 'planned' && entry.day >= today

  return (
    <Sheet title={entryTitle(entry)} onClose={onClose}>
      <div className="stack">
        {state === 'planned' ? <p className="badge">{t('entry.planned')}</p> : null}
        <ul className="list compact">
          {entry.components.map((c) => (
            <li key={c.id} className="component">
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
              ) : own && c.quick ? (
                <label className="amount">
                  <input
                    type="number"
                    inputMode="decimal"
                    min={0}
                    aria-label={t('entry.kcalOf', { name: c.name })}
                    value={energy[c.id] ?? ''}
                    onChange={(e) => setEnergy((v) => ({ ...v, [c.id]: e.target.value }))}
                  />
                  {t('entry.kcalUnit')}
                </label>
              ) : (
                <span className="muted">
                  {c.amount != null ? `${grams(c.amount)} ${c.base_unit ?? ''}` : ''}
                </span>
              )}
              {own && c.quick ? null : <span className="kcal">{kcal(c.nutrients.kcal)}</span>}
              {own && entry.joint && !c.quick ? (
                <label className="amount mine">
                  <span className="muted">{t('entry.iAte')}</span>
                  <input
                    type="number"
                    inputMode="decimal"
                    min={0}
                    aria-label={t('entry.myAmountOf', { name: c.name })}
                    placeholder={t('entry.byShare')}
                    value={weighed[c.id] ?? ''}
                    onChange={(e) => setWeighed((w) => ({ ...w, [c.id]: e.target.value }))}
                  />
                  {c.base_unit}
                </label>
              ) : null}
            </li>
          ))}
        </ul>
        {entry.intake ? (
          <p className="muted">
            {t('totals.kcal', { value: kcalOf(entry.intake) })} · {t('macro.short.protein')}{' '}
            {grams(entry.intake.values.protein)}
          </p>
        ) : null}
        {entry.joint ? (
          <section className="stack shares" aria-label={t('entry.shares')}>
            <h3>{t('entry.shares')}</h3>
            <ul className="list compact">
              {entry.participants.map((p) => (
                <li key={p.user_id} className="row spread">
                  <span>{p.display_name}</span>
                  <span>
                    {t('entry.shareLine', {
                      percent: Math.round(p.share * 100),
                      kcal: kcal(p.intake.values.kcal),
                    })}
                  </span>
                  <small className="muted">{t(`entry.state.${p.state}`)}</small>
                </li>
              ))}
            </ul>
            {own ? (
              <>
                <div className="row wrap" role="group" aria-label={t('entry.myShare')}>
                  {PRESETS.map((p) => (
                    <button
                      key={p}
                      type="button"
                      className="chip"
                      onClick={() => setShareValue(Math.round(p * 100))}
                    >
                      {Math.round(p * 100)} %
                    </button>
                  ))}
                </div>
                <label className="field">
                  <span>{t('entry.myShareValue', { percent: share })}</span>
                  <input
                    type="range"
                    min={5}
                    max={95}
                    step={5}
                    value={share}
                    onChange={(e) => setShareValue(Number(e.target.value))}
                  />
                </label>
                <button
                  type="button"
                  disabled={newShare.isPending || share === myShare}
                  onClick={() => newShare.mutate(share)}
                >
                  {t('entry.applyShare')}
                </button>
              </>
            ) : null}
          </section>
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
              {state === 'planned' && entry.day <= today ? (
                <button type="button" className="primary" onClick={() => eaten.mutate()}>
                  {t('entry.eaten')}
                </button>
              ) : null}
              {state === 'logged' ? (
                <button type="button" onClick={() => notEaten.mutate()}>
                  {t('entry.notEaten')}
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
              {canOffer ? (
                <button type="button" onClick={() => setOffering(true)}>
                  {t('offers.offer')}
                </button>
              ) : null}
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
      {offering && partner ? (
        <OfferSheet
          entryId={entry.id}
          title={entryTitle(entry)}
          partner={partner}
          onClose={() => {
            setOffering(false)
            onClose()
          }}
        />
      ) : null}
    </Sheet>
  )
}
