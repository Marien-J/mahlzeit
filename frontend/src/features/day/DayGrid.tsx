import {
  closestCenter,
  DndContext,
  DragOverlay,
  KeyboardSensor,
  MouseSensor,
  pointerWithin,
  TouchSensor,
  useDndContext,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
  type CollisionDetection,
  type DragEndEvent,
} from '@dnd-kit/core'
import { useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { ErrorMessage } from '../../components/ErrorMessage'
import { grams, kcal, MACROS } from '../../lib/nutrition'
import { moveEntry, useRefreshDays, type Entry, type PersonDay } from './api'
import { EntryCard, entryTitle, isOwn } from './EntryCard'
import { layoutDay, type Cell } from './layout'
import { moveTarget } from './reorder'

const END = 'end-of-day'

// A mouse or finger drops on what is under it, and nowhere else (letting go elsewhere cancels).
// The keyboard has no pointer, so the nearest card wins.
const collision: CollisionDetection = (args) =>
  args.pointerCoordinates ? pointerWithin(args) : closestCenter(args)

type Props = {
  people: PersonDay[]
  day: string
  me: string
  onOpen: (entry: Entry, person: PersonDay) => void
}

/**
 * Both people side by side: totals on top, then the meals in time order. A meal both eat spans
 * both columns. (Households of more than two people get one column each, without spanning.)
 */
export function DayGrid({ people, day, me, onOpen }: Props) {
  const mine = people.find((p) => p.is_me)
  const others = people.filter((p) => !p.is_me)
  if (!mine) return null
  const partner = others.length === 1 ? (others[0] ?? null) : null
  if (others.length > 1)
    return (
      <Dragging mine={mine}>
        <Columns people={people} day={day} me={me} onOpen={onOpen} />
      </Dragging>
    )
  const rows = layoutDay(mine, partner)
  return (
    <Dragging mine={mine}>
      <div className={`day-grid people-${partner ? 2 : 1}`} data-testid="day-grid">
        <Header person={mine} testId="column-me" />
        {partner ? <Header person={partner} testId="column-partner" /> : null}
        {rows.map((row) =>
          row.kind === 'joint' ? (
            <div key={row.key} className="cell joint-cell" data-testid="joint-row">
              <Movable entry={row.mine} me={me} onOpen={() => onOpen(row.mine, mine)} />
            </div>
          ) : (
            <SplitRow
              key={row.key}
              left={row.mine}
              right={partner ? row.theirs : undefined}
              mine={mine}
              partner={partner}
              day={day}
              me={me}
              onOpen={onOpen}
            />
          ),
        )}
        <EndOfDay />
      </div>
    </Dragging>
  )
}

/** Drag my meals into a new order: grab the handle, drop on the meal it should come before. */
function Dragging({ mine, children }: { mine: PersonDay; children: React.ReactNode }) {
  const { t } = useTranslation()
  const refresh = useRefreshDays()
  const [dragged, setDragged] = useState<Entry | null>(null)
  // Mouse and touch apart: a finger must rest on the handle first, so a swipe still scrolls.
  const sensors = useSensors(
    useSensor(MouseSensor, { activationConstraint: { distance: 6 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 200, tolerance: 8 } }),
    useSensor(KeyboardSensor),
  )
  const move = useMutation({
    mutationFn: ({ id, before }: { id: string; before: string | null }) => moveEntry(id, before),
    onSuccess: refresh,
  })
  const order = mine.entries.map((e) => e.id)
  const title = (id: unknown) => {
    const found = mine.entries.find((e) => e.id === id)
    return found ? entryTitle(found) : ''
  }
  const end = (event: DragEndEvent) => {
    setDragged(null)
    const id = String(event.active.id)
    const over = event.over ? String(event.over.id) : undefined
    if (over === undefined) return
    const target = moveTarget(order, id, over === END ? null : over)
    if (target) move.mutate({ id, before: target.before })
  }
  return (
    <DndContext
      sensors={sensors}
      collisionDetection={collision}
      onDragStart={(e) => setDragged(mine.entries.find((x) => x.id === e.active.id) ?? null)}
      onDragEnd={end}
      onDragCancel={() => setDragged(null)}
      accessibility={{
        screenReaderInstructions: { draggable: t('day.dragHelp') },
        announcements: {
          onDragStart: ({ active }) => t('day.dragStart', { name: title(active.id) }),
          onDragOver: ({ active, over }) =>
            over
              ? t('day.dragOver', {
                  name: title(active.id),
                  target: over.id === END ? t('day.dropLast') : title(over.id),
                })
              : '',
          onDragEnd: ({ active }) => t('day.dragEnd', { name: title(active.id) }),
          onDragCancel: ({ active }) => t('day.dragCancel', { name: title(active.id) }),
        },
      }}
    >
      <ErrorMessage error={move.error} />
      {children}
      <DragOverlay>
        {dragged ? <EntryCard entry={dragged} me={mine.user_id} onOpen={() => undefined} /> : null}
      </DragOverlay>
    </DndContext>
  )
}

/** One of my meals: draggable by its handle, and a place another can be dropped before. */
function Movable({ entry, me, onOpen }: { entry: Entry; me: string; onOpen: () => void }) {
  const { t } = useTranslation()
  // dnd-kit hands out callback refs; they are renamed so the refs lint rule sees what they are.
  const { setNodeRef: dropHere, isOver, active } = useDroppable({ id: entry.id })
  const {
    setNodeRef: dragThis,
    setActivatorNodeRef: gripHere,
    listeners,
    attributes,
    isDragging,
  } = useDraggable({ id: entry.id })
  const target = isOver && active?.id !== entry.id
  return (
    <div
      ref={dropHere}
      className={`movable${target ? ' drop-before' : ''}${isDragging ? ' dragging' : ''}`}
    >
      <div ref={dragThis}>
        <EntryCard
          entry={entry}
          me={me}
          onOpen={onOpen}
          handle={
            <button
              type="button"
              className="grip"
              aria-label={t('day.drag', { name: entryTitle(entry) })}
              ref={gripHere}
              {...listeners}
              {...attributes}
            >
              <span className="grip-dots" aria-hidden="true" />
            </button>
          }
        />
      </div>
    </div>
  )
}

/** A drop zone after my last meal, only there while something is being dragged. */
function EndOfDay() {
  const { t } = useTranslation()
  const { active } = useDndContext()
  const { setNodeRef: dropHere, isOver } = useDroppable({ id: END })
  if (!active) return null
  return (
    <div ref={dropHere} className={`drop-end${isOver ? ' over' : ''}`}>
      {t('day.dropLast')}
    </div>
  )
}

function SplitRow({
  left,
  right,
  mine,
  partner,
  day,
  me,
  onOpen,
}: {
  left: Cell | null
  right: Cell | null | undefined
  mine: PersonDay
  partner: PersonDay | null
  day: string
  me: string
  onOpen: Props['onOpen']
}) {
  return (
    <>
      <div className="cell">
        {left ? <CellView cell={left} person={mine} day={day} me={me} onOpen={onOpen} /> : null}
      </div>
      {right !== undefined ? (
        <div className="cell">
          {right && partner ? (
            <CellView cell={right} person={partner} day={day} me={me} onOpen={onOpen} />
          ) : null}
        </div>
      ) : null}
    </>
  )
}

function CellView({
  cell,
  person,
  day,
  me,
  onOpen,
}: {
  cell: Cell
  person: PersonDay
  day: string
  me: string
  onOpen: Props['onOpen']
}) {
  const { t } = useTranslation()
  if (cell.kind === 'entry') {
    const open = () => onOpen(cell.entry, person)
    return isOwn(cell.entry, me) ? (
      <Movable entry={cell.entry} me={me} onOpen={open} />
    ) : (
      <EntryCard entry={cell.entry} me={me} onOpen={open} />
    )
  }
  return (
    <div className="entry empty">
      <span className="time">{cell.at}</span>
      <span className="what">
        {t(`slot.${cell.slot}`)} <span className="muted">—</span>
      </span>
      {person.is_me ? (
        <Link
          to={`/add?day=${day}&slot=${cell.slot}`}
          className="add-here"
          aria-label={t('log.addTo', { slot: t(`slot.${cell.slot}`) })}
        >
          +
        </Link>
      ) : null}
    </div>
  )
}

function Columns({ people, day, me, onOpen }: Props) {
  return (
    <div className="columns">
      {people.map((person) => (
        <div key={person.user_id} className="column">
          <Header person={person} testId={person.is_me ? 'column-me' : 'column-partner'} />
          <div className="timeline">
            {layoutDay(person, null).map((row) =>
              row.kind === 'split' && row.mine ? (
                <div key={row.key}>
                  <CellView cell={row.mine} person={person} day={day} me={me} onOpen={onOpen} />
                </div>
              ) : null,
            )}
          </div>
        </div>
      ))}
    </div>
  )
}

function Header({ person, testId }: { person: PersonDay; testId: string }) {
  return (
    <div className="column-head" data-testid={testId}>
      <h2>{person.display_name}</h2>
      <Totals person={person} />
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
          {person.planned.incomplete.includes('kcal') ? '≈ ' : ''}
          {t('totals.projection', { kcal: kcal(person.projection.kcal) })}
        </p>
      ) : null}
    </div>
  )
}
