import { useMutation } from '@tanstack/react-query'
import { type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { hhmm } from '../../lib/dates'
import { kcal } from '../../lib/nutrition'
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
  return (
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
              {entry.participants
                .map((p) => `${p.display_name} ${Math.round(p.share * 100)} %`)
                .join(' · ')}
            </small>
          ) : null}
        </span>
        <span className="kcal">{kcal(entry.intake?.values.kcal)}</span>
      </button>
      {own && entry.state === 'planned' ? (
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
  )
}
