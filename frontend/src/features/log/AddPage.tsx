import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate, useSearchParams } from 'react-router'
import { api, ApiError, call } from '../../api/client'
import { ErrorMessage } from '../../components/ErrorMessage'
import { Field, SelectField, Toggle } from '../../components/Field'
import { Sheet } from '../../components/Sheet'
import { Star } from '../../components/Star'
import { nowTimeIn, slotForTime, todayIn, type SlotName } from '../../lib/dates'
import { kcal, MACROS } from '../../lib/nutrition'
import { useMe } from '../auth/session'
import {
  draftToItemIn,
  lookupBarcode,
  searchOnline,
  useItemSearch,
  useRecipes,
  useSavedMeals,
  type Draft,
  type Item,
  type ItemIn,
  type Recipe,
} from '../catalogue/api'
import { EMPTY_ITEM, LabelForm } from '../catalogue/LabelForm'
import { logFood, useRefreshDays } from '../day/api'
import { AmountSheet, type Picked } from './AmountSheet'
import { Scanner } from './Scanner'

const MODES = ['search', 'scan', 'quick', 'meals', 'recipes'] as const
type Mode = (typeof MODES)[number]
const SLOTS: SlotName[] = ['breakfast', 'lunch', 'dinner', 'snack']
const DEFAULT_TIMES: Partial<Record<SlotName, string>> = {
  breakfast: '08:00',
  lunch: '12:30',
  dinner: '19:00',
}

export function AddPage() {
  const { t } = useTranslation()
  const me = useMe().data
  const navigate = useNavigate()
  const client = useQueryClient()
  const refresh = useRefreshDays()
  const [params] = useSearchParams()
  const zone = me?.user.time_zone ?? 'Europe/Berlin'
  const now = nowTimeIn(zone)
  const day = params.get('day') ?? todayIn(zone)
  // A plan for today or later: the same screen, but nothing is eaten yet.
  const plan = params.get('plan') === '1'
  const household = useQuery({
    queryKey: ['household'],
    queryFn: () => call(api.GET('/api/household')),
  })
  const hasPartner = (household.data?.members.length ?? 1) > 1
  const [joint, setJoint] = useState(false)
  const [slot, setSlot] = useState<SlotName>(
    (params.get('slot') as SlotName | null) ?? slotForTime(now),
  )
  const [at, setAt] = useState(DEFAULT_TIMES[slot] ?? now)
  const [eatenOut, setEatenOut] = useState(false)
  const [mode, setMode] = useState<Mode>(
    (params.get('mode') as Mode | null) ?? (plan ? 'recipes' : 'search'),
  )
  const [basket, setBasket] = useState<Picked[]>([])
  const [picking, setPicking] = useState<Item | null>(null)
  const [labelling, setLabelling] = useState<{ initial: ItemIn; missing: string[] } | null>(null)

  const back = () =>
    void navigate(
      params.get('from') === 'plan' ? '/plan' : day === todayIn(zone) ? '/' : `/day/${day}`,
    )
  const log = useMutation({
    mutationFn: (items: Picked[]) =>
      logFood({
        day,
        slot,
        at,
        eaten_out: eatenOut,
        portions: 1,
        plan,
        joint,
        components: items.map((p) => p.component),
      }),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ['plan'] })
      await refresh()
      back()
    },
  })
  const logMeal = useMutation({
    mutationFn: (pick: { recipe: string; portions?: number; cooked_grams?: number }) =>
      logFood({
        day,
        slot,
        at,
        eaten_out: eatenOut,
        portions: pick.portions ?? 1,
        cooked_grams: pick.cooked_grams ?? null,
        recipe_id: pick.recipe,
        plan,
        joint,
      }),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ['plan'] })
      await refresh()
      back()
    },
  })

  const onItemSaved = (item: Item) => {
    void client.invalidateQueries({ queryKey: ['items'] })
    setLabelling(null)
    setPicking(item)
  }

  const openDraft = useCallback((draft: Draft) => {
    setLabelling({ initial: draftToItemIn(draft), missing: draft.missing })
  }, [])

  const changeSlot = (s: SlotName) => {
    setSlot(s)
    setAt(DEFAULT_TIMES[s] ?? now)
  }

  if (!me) return null
  return (
    <section className="stack add">
      <header className="row spread">
        <h1>{plan ? t('plan.addTitle') : t('log.title')}</h1>
        <button type="button" onClick={back}>
          {t('common.cancel')}
        </button>
      </header>
      <div className="row">
        <SelectField
          label={t('log.slot')}
          value={slot}
          options={SLOTS.map((s) => ({ value: s, label: t(`slot.${s}`) }))}
          onChange={(v) => changeSlot(v as SlotName)}
        />
        <label className="field">
          <span>{t('log.time')}</span>
          <input type="time" value={at} onChange={(e) => setAt(e.target.value)} />
        </label>
      </div>
      <nav className="tabs" aria-label={t('log.how')}>
        {MODES.map((m) => (
          <button
            key={m}
            type="button"
            aria-pressed={mode === m}
            className={mode === m ? 'active' : undefined}
            onClick={() => setMode(m)}
          >
            {t(`log.mode.${m}`)}
          </button>
        ))}
      </nav>

      {mode === 'search' ? <SearchPanel onPick={setPicking} onDraft={openDraft} /> : null}
      {mode === 'scan' ? (
        <ScanPanel
          onItem={setPicking}
          onDraft={openDraft}
          onUnknown={(code) =>
            setLabelling({
              initial: { ...EMPTY_ITEM, barcodes: [code], source: 'custom' },
              missing: [],
            })
          }
        />
      ) : null}
      {mode === 'quick' ? (
        <QuickAdd
          plan={plan}
          onAdd={(p) => setBasket((b) => [...b, p])}
          onLogNow={(p) => log.mutate([...basket, p])}
          busy={log.isPending}
        />
      ) : null}
      {mode === 'meals' ? (
        <SavedMeals onPick={(id) => logMeal.mutate({ recipe: id })} busy={logMeal.isPending} />
      ) : null}
      {mode === 'recipes' ? (
        <RecipePanel
          joint={joint}
          plan={plan}
          busy={logMeal.isPending}
          onPick={(pick) => logMeal.mutate(pick)}
        />
      ) : null}

      {hasPartner ? (
        <Toggle label={t('entry.together')} checked={joint} onChange={setJoint} />
      ) : null}
      {plan ? null : (
        <Toggle label={t('entry.eatenOut')} checked={eatenOut} onChange={setEatenOut} />
      )}
      <ErrorMessage error={log.error ?? logMeal.error} />

      {basket.length ? (
        <div className="basket" data-testid="basket">
          <ul className="list compact">
            {basket.map((p, i) => (
              <li key={i} className="row spread">
                <span>{p.label}</span>
                <span className="kcal">{kcal(p.kcal)}</span>
                <button
                  type="button"
                  className="icon"
                  aria-label={t('log.remove', { name: p.label })}
                  onClick={() => setBasket((b) => b.filter((_, j) => j !== i))}
                >
                  ×
                </button>
              </li>
            ))}
          </ul>
          <button
            type="button"
            className="primary"
            disabled={log.isPending}
            onClick={() => log.mutate(basket)}
          >
            {t(plan ? 'plan.planBasket' : 'log.logBasket', {
              count: basket.length,
              kcal: kcal(basket.reduce((sum, p) => sum + (p.kcal ?? 0), 0)),
            })}
          </button>
        </div>
      ) : null}

      {picking ? (
        <AmountSheet
          item={picking}
          plan={plan}
          busy={log.isPending}
          onClose={() => setPicking(null)}
          onAdd={(p) => {
            setBasket((b) => [...b, p])
            setPicking(null)
          }}
          onLogNow={(p) => log.mutate([...basket, p])}
        />
      ) : null}
      {labelling ? (
        <Sheet title={t('label.title')} onClose={() => setLabelling(null)}>
          {labelling.missing.length ? <p className="muted">{t('label.completeMissing')}</p> : null}
          <LabelForm
            initial={labelling.initial}
            missing={labelling.missing}
            language={me.user.language}
            onSaved={onItemSaved}
          />
        </Sheet>
      ) : null}
    </section>
  )
}

function SearchPanel({
  onPick,
  onDraft,
}: {
  onPick: (item: Item) => void
  onDraft: (d: Draft) => void
}) {
  const { t } = useTranslation()
  const [query, setQuery] = useState('')
  const search = useItemSearch(query)
  const online = useMutation({ mutationFn: () => searchOnline(query) })
  return (
    <div className="stack">
      <Field
        label={t('log.search')}
        type="search"
        autoFocus
        autoComplete="off"
        value={query}
        onChange={(e) => {
          setQuery(e.target.value)
          online.reset()
        }}
      />
      {!query ? <p className="muted">{t('log.favouritesAndRecent')}</p> : null}
      <ul className="list results" data-testid="results">
        {(search.data ?? []).map((item) => (
          <li key={item.id}>
            <button type="button" className="result" onClick={() => onPick(item)}>
              <span>
                {item.favourite ? <Star /> : null}
                {item.name}
                {item.brand ? <small className="muted"> · {item.brand}</small> : null}
              </span>
              <small className="muted">
                {t('amount.per100', { unit: item.base_unit, kcal: kcal(item.nutrients.kcal) })}
              </small>
            </button>
          </li>
        ))}
      </ul>
      {query.trim().length >= 2 ? (
        <button type="button" onClick={() => online.mutate()} disabled={online.isPending}>
          {t('log.searchOnline', { query })}
        </button>
      ) : null}
      <ErrorMessage error={online.error} />
      {online.data ? (
        online.data.length ? (
          <ul className="list results">
            {online.data.map((d) => (
              <li key={d.barcode}>
                <button type="button" className="result" onClick={() => onDraft(d)}>
                  <span>
                    {d.names.de ?? d.names.en ?? d.names.nl}
                    {d.brand ? <small className="muted"> · {d.brand}</small> : null}
                  </span>
                  <small className="muted">{t('log.fromOpenFoodFacts')}</small>
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">{t('log.nothingOnline')}</p>
        )
      ) : null}
    </div>
  )
}

function ScanPanel({
  onItem,
  onDraft,
  onUnknown,
}: {
  onItem: (item: Item) => void
  onDraft: (d: Draft) => void
  onUnknown: (code: string) => void
}) {
  const { t } = useTranslation()
  const [error, setError] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)
  const handle = useCallback(
    async (code: string) => {
      setBusy(true)
      setError(null)
      try {
        const result = await lookupBarcode(code)
        if (result.item) onItem(result.item)
        else if (result.draft) onDraft(result.draft)
        else onUnknown(code)
      } catch (err) {
        // Offline or Open Food Facts down: enter the label by hand.
        if (err instanceof ApiError && err.code === 'off_unavailable') onUnknown(code)
        else setError(err)
      } finally {
        setBusy(false)
      }
    },
    [onItem, onDraft, onUnknown],
  )
  return (
    <div className="stack">
      <Scanner onCode={(c) => void handle(c)} />
      {busy ? <p className="muted">{t('scan.lookingUp')}</p> : null}
      <ErrorMessage error={error} />
    </div>
  )
}

function QuickAdd({
  plan,
  onAdd,
  onLogNow,
  busy,
}: {
  plan: boolean
  onAdd: (p: Picked) => void
  onLogNow: (p: Picked) => void
  busy: boolean
}) {
  const { t } = useTranslation()
  const [form, setForm] = useState({ name: '', kcal: '', protein: '', carbs: '', fat: '' })
  const n = (v: string) => (v.trim() ? Number(v.replace(',', '.')) : null)
  const picked = (): Picked => ({
    component: {
      quick_name: form.name.trim(),
      kcal: n(form.kcal),
      protein: n(form.protein),
      carbs: n(form.carbs),
      fat: n(form.fat),
    },
    label: form.name.trim(),
    kcal: n(form.kcal),
  })
  const submit = (e: FormEvent) => {
    e.preventDefault()
    onLogNow(picked())
  }
  return (
    <form className="stack" onSubmit={submit}>
      <Field
        label={t('quick.name')}
        required
        value={form.name}
        onChange={(e) => setForm({ ...form, name: e.target.value })}
      />
      <Field
        label={t('quick.kcal')}
        required={!plan}
        hint={plan ? t('quick.kcalOptionalWhenPlanning') : undefined}
        inputMode="decimal"
        value={form.kcal}
        onChange={(e) => setForm({ ...form, kcal: e.target.value })}
      />
      <div className="row">
        {MACROS.map((m) => (
          <Field
            key={m}
            label={t(`nutrient.${m}`)}
            inputMode="decimal"
            value={form[m]}
            onChange={(e) => setForm({ ...form, [m]: e.target.value })}
          />
        ))}
      </div>
      <div className="row">
        <button
          type="button"
          disabled={!form.name || (!plan && !form.kcal) || busy}
          onClick={() => onAdd(picked())}
        >
          {t('amount.addMore')}
        </button>
        <button type="submit" className="primary" disabled={busy || (plan && !form.name.trim())}>
          {t(plan ? 'amount.planNow' : 'amount.logNow')}
        </button>
      </div>
    </form>
  )
}

function SavedMeals({ onPick, busy }: { onPick: (id: string) => void; busy: boolean }) {
  const { t } = useTranslation()
  const meals = useSavedMeals()
  if (meals.data && meals.data.length === 0) return <p className="muted">{t('meals.none')}</p>
  return (
    <ul className="list results">
      {(meals.data ?? []).map((m) => (
        <li key={m.id}>
          <button type="button" className="result" disabled={busy} onClick={() => onPick(m.id)}>
            <span>{m.name}</span>
            <small className="muted">
              {t('totals.kcal', { value: kcal(m.per_serving.values.kcal) })}
            </small>
          </button>
        </li>
      ))}
    </ul>
  )
}

/** Recipes, staples first. A portion can be given as a number or, with a cooked yield, as the
 * weight of the cooked dish on the plate. */
function RecipePanel({
  joint,
  plan,
  busy,
  onPick,
}: {
  joint: boolean
  plan: boolean
  busy: boolean
  onPick: (pick: { recipe: string; portions?: number; cooked_grams?: number }) => void
}) {
  const { t } = useTranslation()
  const recipes = useRecipes('recipe')
  const [open, setOpen] = useState<Recipe | null>(null)
  if (recipes.data && recipes.data.length === 0) return <p className="muted">{t('recipes.none')}</p>
  return (
    <>
      <ul className="list results" data-testid="recipe-picks">
        {(recipes.data ?? []).map((r) => (
          <li key={r.id}>
            <button type="button" className="result" disabled={busy} onClick={() => setOpen(r)}>
              <span>
                {r.staple ? <Star /> : null}
                {r.name}
              </span>
              <small className="muted">
                {t('recipes.perServing', { kcal: kcal(r.per_serving.values.kcal) })}
              </small>
            </button>
          </li>
        ))}
      </ul>
      {open ? (
        <PortionSheet
          recipe={open}
          joint={joint}
          plan={plan}
          busy={busy}
          onPick={onPick}
          onClose={() => setOpen(null)}
        />
      ) : null}
    </>
  )
}

function PortionSheet({
  recipe,
  joint,
  plan,
  busy,
  onPick,
  onClose,
}: {
  recipe: Recipe
  joint: boolean
  plan: boolean
  busy: boolean
  onPick: (pick: { recipe: string; portions?: number; cooked_grams?: number }) => void
  onClose: () => void
}) {
  const { t } = useTranslation()
  // Both of us eating one dish: two portions by default.
  const [portions, setPortions] = useState(joint ? '2' : '1')
  const [cooked, setCooked] = useState('')
  const number = (v: string) => Number(v.replace(',', '.'))
  const byWeight = cooked.trim() !== ''
  const valid = byWeight ? number(cooked) > 0 : number(portions) > 0
  return (
    <Sheet title={recipe.name} onClose={onClose}>
      <form
        className="stack"
        onSubmit={(e) => {
          e.preventDefault()
          if (!valid) return
          onPick(
            byWeight
              ? { recipe: recipe.id, cooked_grams: number(cooked) }
              : { recipe: recipe.id, portions: number(portions) },
          )
        }}
      >
        <Field
          label={t('recipes.servings')}
          inputMode="decimal"
          value={portions}
          disabled={byWeight}
          onChange={(e) => setPortions(e.target.value)}
        />
        {recipe.cooked_yield_g != null ? (
          <Field
            label={t('recipes.cookedWeight')}
            inputMode="decimal"
            value={cooked}
            onChange={(e) => setCooked(e.target.value)}
          />
        ) : null}
        <button type="submit" className="primary" disabled={!valid || busy}>
          {t(plan ? 'amount.planNow' : 'amount.logNow')}
        </button>
      </form>
    </Sheet>
  )
}
