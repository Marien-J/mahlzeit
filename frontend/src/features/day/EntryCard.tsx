import { useMutation } from '@tanstack/react-query'
import { type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { ErrorMessage } from '../../components/ErrorMessage'
import { hhmm, todayIn } from '../../lib/dates'
import { kcalOf } from '../../lib/nutrition'
import { useMe } from '../auth/session'
import { setEntryState, useRefreshDays, type Entry } from './api'

export function entryTitle(entry: Entry): string {
  return entry.name || entry.components.map((c) => c.name).join(', ')
}

export const isOwn = (entry: Entry, me: string) => entry.participants.some((p) => p.user_id === me)

/** One meal in the timeline: open it, mark it eaten with one tap, drag it by its handle. */
export function EntryCard({
  entry,
  me,
  onOpen,
  handle,
}: {
  entry: Entry
  me: string
  onOpen: () => void
  handle?: ReactNode
}) {
  const { t } = useTranslation()
  const refresh = useRefreshDays()
  const eaten = useMutation({
    mutationFn: () => setEntryState(entry.id, 'logged'),
    onSuccess: refresh,
  })
  const own = isOwn(entry, me)
  const zone = useMe().data?.user.time_zone
  // A later day only holds plans: nothing there can be eaten yet.
  const due = zone ? entry.day <= todayIn(zone) : true
  return (
    <>
      <div className={`entry-card ${entry.state ?? ''}${entry.joint ? ' joint' : ''}`}>
        {handle}
        <button type="button" className={`entry ${entry.state ?? ''}`} onClick={onOpen}>
          <span className="time">{hhmm(entry.at)}</span>
          <span className="what">
            <small className="muted">
              {t(`slot.${entry.slot}`)}
              {entry.joint ? ` · ${t('entry.jointShort')}` : ''}
            </small>
            <span>{entryTitle(entry)}</span>
            {entry.joint ? (
              <small className="muted shares">
                {[...entry.participants]
                  .sort((x, y) => Number(y.user_id === me) - Number(x.user_id === me))
                  .map((p) => `${p.display_name} ${Math.round(p.share * 100)} %`)
                  .join(' · ')}
              </small>
            ) : null}
          </span>
          <span className="kcal">{kcalOf(entry.intake)}</span>
        </button>
        {own && entry.state === 'planned' && due ? (
          <button
            type="button"
            className="eaten"
            aria-label={t('entry.eatenFor', { name: entryTitle(entry) })}
            disabled={eaten.isPending}
            onClick={() => eaten.mutate()}
          >
            <span className="check" aria-hidden="true" />
          </button>
        ) : null}
      </div>
      <ErrorMessage error={eaten.error} />
    </>
  )
}
