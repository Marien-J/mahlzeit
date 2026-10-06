import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { hhmm, type SlotName } from '../../lib/dates'
import { grams, kcal, MACROS } from '../../lib/nutrition'
import type { Entry, PersonDay } from './api'

const ANCHORS: { slot: SlotName; at: string }[] = [
  { slot: 'breakfast', at: '08:00' },
  { slot: 'lunch', at: '12:30' },
  { slot: 'dinner', at: '19:00' },
]

type Row = { kind: 'entry'; entry: Entry } | { kind: 'empty'; slot: SlotName; at: string }

/** Entries in time order, with a dash where an anchor meal has nothing yet. */
export function rowsFor(person: PersonDay): Row[] {
  const rows: Row[] = person.entries.map((entry) => ({ kind: 'entry', entry }))
  for (const anchor of ANCHORS) {
    if (!person.entries.some((e) => e.slot === anchor.slot)) rows.push({ kind: 'empty', ...anchor })
  }
  const time = (r: Row) => (r.kind === 'entry' ? hhmm(r.entry.at) : r.at)
  return rows.sort((a, b) => time(a).localeCompare(time(b)))
}

export function entryTitle(entry: Entry): string {
  return entry.name || entry.components.map((c) => c.name).join(', ')
}

export function PersonColumn({
  person,
  day,
  onOpen,
}: {
  person: PersonDay
  day: string
  onOpen: (entry: Entry) => void
}) {
  const { t } = useTranslation()
  return (
    <div className="column" data-testid={person.is_me ? 'column-me' : 'column-partner'}>
      <h2>{person.display_name}</h2>
      <Totals person={person} />
      <ol className="timeline">
        {rowsFor(person).map((row) =>
          row.kind === 'empty' ? (
            <li key={`empty-${row.slot}`} className="entry empty">
              <span className="time">{row.at}</span>
              <span className="what">
                {t(`slot.${row.slot}`)} <span className="muted">—</span>
              </span>
              {person.is_me ? (
                <Link
                  to={`/add?day=${day}&slot=${row.slot}`}
                  className="add-here"
                  aria-label={t('log.addTo', { slot: t(`slot.${row.slot}`) })}
                >
                  +
                </Link>
              ) : null}
            </li>
          ) : (
            <li key={row.entry.id}>
              <button
                type="button"
                className={`entry ${row.entry.state ?? ''}`}
                onClick={() => onOpen(row.entry)}
              >
                <span className="time">{hhmm(row.entry.at)}</span>
                <span className="what">
                  <small className="muted">{t(`slot.${row.entry.slot}`)}</small>
                  <span>{entryTitle(row.entry)}</span>
                </span>
                <span className="kcal">{kcal(row.entry.intake?.values.kcal)}</span>
              </button>
            </li>
          ),
        )}
      </ol>
    </div>
  )
}

function Totals({ person }: { person: PersonDay }) {
  const { t } = useTranslation()
  const logged = person.logged.values
  const target = person.targets
  const approx = person.logged.incomplete.includes('kcal') ? '≈ ' : ''
  return (
    <div className="totals" data-testid="totals">
      <p className="big">
        {approx}
        {target?.kcal != null
          ? t('totals.ofTarget', { value: kcal(logged.kcal), target: kcal(target.kcal) })
          : t('totals.kcal', { value: kcal(logged.kcal) })}
      </p>
      <p className="macros">
        {MACROS.map((m) => (
          <span key={m}>
            {t(`macro.short.${m}`)} {grams(logged[m])}
            {target?.[m] != null ? `/${grams(target[m])}` : ''}
          </span>
        ))}
      </p>
      {person.remaining ? (
        <p className="left" data-testid="remaining">
          {t('totals.left', {
            kcal: kcal(person.remaining.kcal),
            protein: grams(person.remaining.protein),
          })}
        </p>
      ) : null}
      {person.projection && person.planned.values.kcal ? (
        <p className="muted projection">
          {t('totals.projection', { kcal: kcal(person.projection.kcal) })}
        </p>
      ) : null}
    </div>
  )
}
