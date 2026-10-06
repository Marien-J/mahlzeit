import { useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate, useParams } from 'react-router'
import { ErrorMessage } from '../../components/ErrorMessage'
import { Sheet } from '../../components/Sheet'
import { formatDate } from '../../i18n/format'
import { addDays, dayAsDate, todayIn } from '../../lib/dates'
import { useMe } from '../auth/session'
import { copyDay, setDayType, useDay, useRefreshDays, type Entry, type PersonDay } from './api'
import { EntrySheet } from './EntrySheet'
import { PersonColumn } from './PersonColumn'

export function DayPage() {
  const { t } = useTranslation()
  const me = useMe().data
  const params = useParams()
  const navigate = useNavigate()
  const today = me ? todayIn(me.user.time_zone) : ''
  const day = params.day ?? today
  const query = useDay(day)
  const refresh = useRefreshDays()
  const [open, setOpen] = useState<{ entry: Entry; person: PersonDay } | null>(null)
  const [copying, setCopying] = useState(false)
  const dayType = useMutation({
    mutationFn: (type: 'training' | 'rest') => setDayType(day, type),
    onSuccess: refresh,
  })
  if (!me) return null

  const go = (target: string) => void navigate(target === today ? '/' : `/day/${target}`)
  const self = query.data?.people.find((p) => p.is_me)
  const longDate = formatDate(dayAsDate(day), { dateStyle: 'full', timeZone: 'UTC' })

  return (
    <section className="day">
      <header className="day-nav">
        <button
          type="button"
          className="icon"
          aria-label={t('day.previous')}
          onClick={() => go(addDays(day, -1))}
        >
          ‹
        </button>
        <div className="day-title">
          <h1>{day === today ? t('day.today') : longDate}</h1>
          {day === today ? <span className="muted">{longDate}</span> : null}
        </div>
        <button
          type="button"
          className="icon"
          aria-label={t('day.next')}
          onClick={() => go(addDays(day, 1))}
        >
          ›
        </button>
      </header>
      <div className="row spread">
        {self ? (
          <button
            type="button"
            className={`chip ${self.day_type}`}
            disabled={dayType.isPending}
            onClick={() => dayType.mutate(self.day_type === 'training' ? 'rest' : 'training')}
          >
            {t(`dayType.${self.day_type}`)}
          </button>
        ) : (
          <span />
        )}
        <div className="row">
          {day !== today ? (
            <button type="button" onClick={() => go(today)}>
              {t('day.today')}
            </button>
          ) : null}
          <button type="button" onClick={() => setCopying(true)}>
            {t('day.copyFrom')}
          </button>
        </div>
      </div>
      <ErrorMessage error={query.error ?? dayType.error} />
      {query.data ? (
        <div className="columns">
          {query.data.people.map((person) => (
            <PersonColumn
              key={person.user_id}
              person={person}
              day={day}
              onOpen={(entry) => setOpen({ entry, person })}
            />
          ))}
        </div>
      ) : (
        <p className="muted">{t('app.loading')}</p>
      )}
      <Link className="fab" to={`/add?day=${day}`} aria-label={t('log.add')}>
        +
      </Link>
      {open ? (
        <EntrySheet
          entry={open.entry}
          own={open.person.is_me}
          today={today}
          onClose={() => setOpen(null)}
        />
      ) : null}
      {copying ? <CopyDaySheet day={day} onClose={() => setCopying(false)} /> : null}
    </section>
  )
}

function CopyDaySheet({ day, onClose }: { day: string; onClose: () => void }) {
  const { t } = useTranslation()
  const refresh = useRefreshDays()
  const [source, setSource] = useState(addDays(day, -1))
  const copy = useMutation({
    mutationFn: () => copyDay(day, source),
    onSuccess: async () => {
      await refresh()
      onClose()
    },
  })
  return (
    <Sheet title={t('day.copyFrom')} onClose={onClose}>
      <form
        className="stack"
        onSubmit={(e) => {
          e.preventDefault()
          copy.mutate()
        }}
      >
        <p className="muted">{t('day.copyExplain')}</p>
        <label className="field">
          <span>{t('day.sourceDay')}</span>
          <input type="date" value={source} max={day} onChange={(e) => setSource(e.target.value)} />
        </label>
        <ErrorMessage error={copy.error} />
        <button type="submit" className="primary" disabled={copy.isPending}>
          {t('day.copy')}
        </button>
      </form>
    </Sheet>
  )
}
