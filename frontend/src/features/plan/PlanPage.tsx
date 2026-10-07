import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { ErrorMessage } from '../../components/ErrorMessage'
import { formatDate } from '../../i18n/format'
import { addDays, dayAsDate, hhmm, todayIn } from '../../lib/dates'
import { grams, kcal } from '../../lib/nutrition'
import { useMe } from '../auth/session'
import { usePlan, type Plan } from './api'

type PlanEntry = Plan['days'][number]['entries'][number]

const HORIZON = 31 // today and 30 days ahead
const STEP = 14

function title(entry: PlanEntry): string {
  return entry.name || entry.components.map((c) => c.name).join(', ')
}

/** The coming days, both people's meals: plan dinners from staple recipes, see who eats what. */
export function PlanPage() {
  const { t } = useTranslation()
  const me = useMe().data
  const [days, setDays] = useState(STEP)
  const today = me ? todayIn(me.user.time_zone) : ''
  const plan = usePlan(today, days)
  if (!me) return null

  const offered = new Set(plan.data?.offers.map((o) => o.meal?.id).filter(Boolean))
  // Me first, then the others, the same on every row.
  const rank = new Map(plan.data?.members.map((m, i) => [m.user_id, i]))
  const names = (e: PlanEntry) =>
    [...e.participants]
      .sort((a, b) => (rank.get(a.user_id) ?? 0) - (rank.get(b.user_id) ?? 0))
      .map((p) => p.display_name)
      .join(' & ')
  const label = (day: string) =>
    day === today
      ? t('day.today')
      : day === addDays(today, 1)
        ? t('plan.tomorrow')
        : formatDate(dayAsDate(day), {
            dateStyle: undefined,
            weekday: 'long',
            day: 'numeric',
            month: 'short',
            timeZone: 'UTC',
          })

  return (
    <section className="stack plan">
      <header className="row spread">
        <h1>{t('plan.title')}</h1>
        <Link to="/recipes">{t('recipes.title')}</Link>
      </header>
      <ErrorMessage error={plan.error} />
      {plan.data ? (
        <ol className="plan-days">
          {plan.data.days.map((d) => (
            <li key={d.day} data-testid={`plan-${d.day}`} className="plan-day">
              <div className="row spread">
                <h2>
                  <Link to={d.day === today ? '/' : `/day/${d.day}`}>{label(d.day)}</Link>
                </h2>
                <Link
                  className="add-here"
                  to={`/add?day=${d.day}&slot=dinner&plan=1&from=plan`}
                  aria-label={t('plan.planFor', { day: label(d.day) })}
                >
                  +
                </Link>
              </div>
              {d.entries.length === 0 ? (
                <p className="muted">{t('plan.nothing')}</p>
              ) : (
                <ul className="plan-entries">
                  {d.entries.map((e) => (
                    <li key={e.id} className={`plan-entry ${e.participants[0]?.state ?? ''}`}>
                      <Link to={d.day === today ? '/' : `/day/${d.day}`}>
                        <span className="time">{hhmm(e.at)}</span>
                        <span className="what">
                          <small className="muted">
                            {t(`slot.${e.slot}`)} · {names(e)}
                          </small>
                          <span>{title(e)}</span>
                        </span>
                        <span className="kcal">
                          {e.dish.values.kcal != null
                            ? t('plan.dishKcal', { kcal: kcal(e.dish.values.kcal) })
                            : '–'}
                        </span>
                      </Link>
                      {offered.has(e.id) ? (
                        <small className="badge">{t('plan.offered')}</small>
                      ) : null}
                      {e.dish.values.protein != null ? (
                        <small className="muted">
                          {t('macro.short.protein')} {grams(e.dish.values.protein)}
                        </small>
                      ) : null}
                    </li>
                  ))}
                </ul>
              )}
            </li>
          ))}
        </ol>
      ) : (
        <p className="muted">{t('app.loading')}</p>
      )}
      {days < HORIZON ? (
        <button type="button" onClick={() => setDays((d) => Math.min(HORIZON, d + STEP))}>
          {t('plan.more')}
        </button>
      ) : null}
    </section>
  )
}
