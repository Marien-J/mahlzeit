import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { api, call, type Schemas } from '../../api/client'
import { ErrorMessage } from '../../components/ErrorMessage'
import { Field, Toggle } from '../../components/Field'
import { formatDate } from '../../i18n/format'
import { addDays, dayAsDate, todayIn } from '../../lib/dates'
import { grams, kcal } from '../../lib/nutrition'
import { useMe } from '../auth/session'

type Plan = Schemas['TargetPlanOut']
type TargetSet = Schemas['TargetSetOut']
type DayType = 'training' | 'rest'
const FIELDS = ['kcal', 'protein', 'carbs', 'fat'] as const
type Values = Record<(typeof FIELDS)[number], string>
// 2024-01-01 was a Monday; the pattern starts on Monday.
const MONDAY = '2024-01-01'
const WEEKDAY: Intl.DateTimeFormatOptions = {
  dateStyle: undefined,
  weekday: 'short',
  timeZone: 'UTC',
}

const planKey = ['targets'] as const

function useTargetPlan() {
  return useQuery({ queryKey: planKey, queryFn: () => call(api.GET('/api/targets')) })
}

/** The set in force on `day` for one day type: the newest one that started on or before it. */
export function current(history: TargetSet[], dayType: DayType, day: string): TargetSet | null {
  return (
    history
      .filter((s) => s.day_type === dayType && s.valid_from <= day)
      .sort((a, b) => b.valid_from.localeCompare(a.valid_from))[0] ?? null
  )
}

function toValues(set: TargetSet | null): Values {
  const v = (n: number | null | undefined) => (n == null ? '' : String(n))
  return {
    kcal: v(set?.targets.kcal),
    protein: v(set?.targets.protein),
    carbs: v(set?.targets.carbs),
    fat: v(set?.targets.fat),
  }
}

export function TargetsPage() {
  const { t } = useTranslation()
  const me = useMe().data
  const plan = useTargetPlan()
  if (!me) return null
  return (
    <section className="stack">
      <h1>{t('targets.title')}</h1>
      <p className="muted">{t('targets.intro')}</p>
      <ErrorMessage error={plan.error} />
      {plan.data ? (
        <>
          <WeekPattern plan={plan.data} />
          <TargetsForm plan={plan.data} today={todayIn(me.user.time_zone)} />
          <History plan={plan.data} />
        </>
      ) : null}
      <Link to="/settings">{t('common.back')}</Link>
    </section>
  )
}

function WeekPattern({ plan }: { plan: Plan }) {
  const { t } = useTranslation()
  const client = useQueryClient()
  const save = useMutation({
    mutationFn: (pattern: string) =>
      call(api.PUT('/api/targets/week-pattern', { body: { pattern } })),
    onSuccess: (data) => {
      client.setQueryData(planKey, data)
      void client.invalidateQueries({ queryKey: ['day'] })
    },
  })
  const pattern = save.variables && save.isPending ? save.variables : plan.week_pattern
  const flip = (i: number) =>
    save.mutate(
      pattern
        .split('')
        .map((c, j) => (j === i ? (c === 'T' ? 'R' : 'T') : c))
        .join(''),
    )
  return (
    <>
      <h2>{t('targets.week')}</h2>
      <p className="muted">{t('targets.weekHint')}</p>
      <div className="week" role="group" aria-label={t('targets.week')}>
        {pattern.split('').map((c, i) => {
          const weekday = formatDate(dayAsDate(addDays(MONDAY, i)), WEEKDAY)
          return (
            <button
              key={i}
              type="button"
              aria-pressed={c === 'T'}
              className={c === 'T' ? 'active' : undefined}
              aria-label={`${weekday}: ${t(c === 'T' ? 'dayType.training' : 'dayType.rest')}`}
              onClick={() => flip(i)}
            >
              <span>{weekday}</span>
              <small>{t(c === 'T' ? 'dayType.trainingShort' : 'dayType.restShort')}</small>
            </button>
          )
        })}
      </div>
      <ErrorMessage error={save.error} />
    </>
  )
}

function TargetsForm({ plan, today }: { plan: Plan; today: string }) {
  const { t } = useTranslation()
  const client = useQueryClient()
  const training = current(plan.history, 'training', today)
  const rest = current(plan.history, 'rest', today)
  const [values, setValues] = useState<Record<DayType, Values>>({
    training: toValues(training),
    rest: toValues(rest),
  })
  const [same, setSame] = useState(
    JSON.stringify(toValues(training)) === JSON.stringify(toValues(rest)),
  )
  const [validFrom, setValidFrom] = useState(today)
  const n = (v: string) => (v.trim() ? Number(v.replace(',', '.')) : null)
  const body = (v: Values, dayTypes: DayType[]) => ({
    kcal: n(v.kcal),
    protein: n(v.protein),
    carbs: n(v.carbs),
    fat: n(v.fat),
    day_types: dayTypes,
    valid_from: validFrom,
  })
  const save = useMutation({
    mutationFn: async () => {
      if (same)
        return call(api.PUT('/api/targets', { body: body(values.training, ['training', 'rest']) }))
      await call(api.PUT('/api/targets', { body: body(values.training, ['training']) }))
      return call(api.PUT('/api/targets', { body: body(values.rest, ['rest']) }))
    },
    onSuccess: (data) => {
      client.setQueryData(planKey, data)
      void client.invalidateQueries({ queryKey: ['day'] })
    },
  })
  const submit = (e: FormEvent) => {
    e.preventDefault()
    save.mutate()
  }
  const set = (dayType: DayType, field: keyof Values, value: string) =>
    setValues((v) => ({ ...v, [dayType]: { ...v[dayType], [field]: value } }))
  const shown: DayType[] = same ? ['training'] : ['training', 'rest']
  return (
    <form className="stack" onSubmit={submit}>
      <h2>{t('targets.daily')}</h2>
      <Toggle label={t('targets.same')} checked={same} onChange={setSame} />
      {shown.map((dayType) => (
        <fieldset key={dayType} className="card">
          <legend>{same ? t('targets.everyDay') : t(`dayType.${dayType}`)}</legend>
          <div className="grid4">
            {FIELDS.map((f) => (
              <Field
                key={f}
                label={t(`targets.field.${f}`)}
                inputMode="decimal"
                value={values[dayType][f]}
                onChange={(e) => set(dayType, f, e.target.value)}
              />
            ))}
          </div>
        </fieldset>
      ))}
      <Field
        label={t('targets.validFrom')}
        type="date"
        required
        value={validFrom}
        onChange={(e) => setValidFrom(e.target.value)}
        hint={t('targets.validFromHint')}
      />
      <ErrorMessage error={save.error} />
      {save.isSuccess ? <p role="status">{t('targets.saved')}</p> : null}
      <button type="submit" className="primary" disabled={save.isPending}>
        {t('common.save')}
      </button>
    </form>
  )
}

function History({ plan }: { plan: Plan }) {
  const { t } = useTranslation()
  if (!plan.history.length) return null
  const sorted = [...plan.history].sort(
    (a, b) => b.valid_from.localeCompare(a.valid_from) || a.day_type.localeCompare(b.day_type),
  )
  return (
    <>
      <h2>{t('targets.history')}</h2>
      <ul className="list compact" data-testid="target-history">
        {sorted.map((s) => (
          <li key={`${s.valid_from}-${s.day_type}`} className="row spread">
            <span>
              {formatDate(dayAsDate(s.valid_from), { timeZone: 'UTC' })} ·{' '}
              {t(`dayType.${s.day_type}`)}
            </span>
            <span className="muted">
              {t('targets.summary', {
                kcal: kcal(s.targets.kcal),
                protein: grams(s.targets.protein),
                carbs: grams(s.targets.carbs),
                fat: grams(s.targets.fat),
              })}
            </span>
          </li>
        ))}
      </ul>
    </>
  )
}
