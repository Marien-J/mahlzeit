import { useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { ErrorMessage } from '../../components/ErrorMessage'
import { formatDate } from '../../i18n/format'
import {
  STATUSES,
  adjustStock,
  amountText,
  checkAisle,
  nextStatus,
  useRefreshStock,
  useStock,
  type StockData,
  type StockRow,
  type StockStatus,
} from './api'
import { PurchaseSheet } from './PurchaseSheet'
import { StockItemSheet } from './StockItemSheet'

type Aisle = { category: string; rows: StockRow[] }

function aisles(rows: StockRow[]): Aisle[] {
  const result: Aisle[] = []
  for (const row of rows) {
    const last = result[result.length - 1]
    if (last && last.category === row.category) last.rows.push(row)
    else result.push({ category: row.category, rows: [row] })
  }
  return result
}

/** What is in the house, aisle by aisle. Stock is advisory: roughly right beats exact. */
export function StockPage() {
  const { t } = useTranslation()
  const stock = useStock()
  const [open, setOpen] = useState<StockRow | null>(null)
  const [adding, setAdding] = useState(false)
  const [checking, setChecking] = useState<string | null>(null)
  const data = stock.data
  return (
    <section className="stack stock">
      <header className="row spread">
        <h1>{t('stock.title')}</h1>
        <div className="row">
          <Link to="/stock/report">{t('report.title')}</Link>
          <button type="button" className="primary" onClick={() => setAdding(true)}>
            {t('purchase.add')}
          </button>
        </div>
      </header>
      <ErrorMessage error={stock.error} />
      {!data ? <p className="muted">{t('app.loading')}</p> : null}
      {data && data.rows.length === 0 ? <p className="muted">{t('stock.empty')}</p> : null}
      {data
        ? aisles(data.rows).map((aisle) => (
            <AisleSection
              key={aisle.category}
              aisle={aisle}
              data={data}
              checking={checking === aisle.category}
              onCheck={() => setChecking(aisle.category)}
              onDone={() => setChecking(null)}
              onOpen={setOpen}
            />
          ))
        : null}
      {open ? <StockItemSheet row={open} onClose={() => setOpen(null)} /> : null}
      {adding ? <PurchaseSheet onClose={() => setAdding(false)} /> : null}
    </section>
  )
}

function AisleSection({
  aisle,
  data,
  checking,
  onCheck,
  onDone,
  onOpen,
}: {
  aisle: Aisle
  data: StockData
  checking: boolean
  onCheck: () => void
  onDone: () => void
  onOpen: (row: StockRow) => void
}) {
  const { t } = useTranslation()
  const name = t(`category.${aisle.category}`)
  const checked = data.checks.find((c) => c.category === aisle.category)
  return (
    <section className="aisle stock-aisle" aria-label={name}>
      <div className="row spread wrap">
        <h2>{name}</h2>
        {checking ? null : (
          <div className="row">
            {checked ? (
              <small className="muted">
                {t('stock.checkedOn', {
                  date: formatDate(checked.checked_at, { dateStyle: 'medium' }),
                })}
              </small>
            ) : null}
            <button
              type="button"
              aria-label={t('stock.checkAisle', { aisle: name })}
              onClick={onCheck}
            >
              {t('stock.check')}
            </button>
          </div>
        )}
      </div>
      {checking ? (
        <PantryCheck aisle={aisle} name={name} onDone={onDone} />
      ) : (
        <ul className="list-rows">
          {aisle.rows.map((row) => (
            <StockLine key={row.item_id} row={row} onOpen={() => onOpen(row)} />
          ))}
        </ul>
      )}
    </section>
  )
}

function StockLine({ row, onOpen }: { row: StockRow; onOpen: () => void }) {
  const { t } = useTranslation()
  const refresh = useRefreshStock()
  const flip = useMutation({
    mutationFn: (status: StockStatus) => adjustStock(row.item_id, { status }),
    onSuccess: refresh,
  })
  return (
    <li className="list-row stock-row">
      <button type="button" className="what" onClick={onOpen}>
        <span>{row.name}</span>
      </button>
      {row.mode === 'status' ? (
        <button
          type="button"
          className={`status ${row.status ?? 'ok'}`}
          aria-label={t('stock.statusOf', {
            name: row.name,
            status: t(`stock.status.${row.status ?? 'ok'}`),
          })}
          disabled={flip.isPending}
          onClick={() => flip.mutate(nextStatus(row.status))}
        >
          {t(`stock.status.${row.status ?? 'ok'}`)}
        </button>
      ) : (
        <span className={row.level ? 'level' : 'level none'}>
          {amountText(row.level ?? 0, row.base_unit)}
        </span>
      )}
    </li>
  )
}

/**
 * The pantry check of one aisle: steppers for amounts, three taps for statuses, then one call
 * that sends what changed and marks the aisle checked. Built for thirty items in two minutes.
 */
function PantryCheck({ aisle, name, onDone }: { aisle: Aisle; name: string; onDone: () => void }) {
  const { t } = useTranslation()
  const refresh = useRefreshStock()
  const [counts, setCounts] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      aisle.rows.filter((r) => r.mode === 'counted').map((r) => [r.item_id, String(r.level ?? 0)]),
    ),
  )
  const [statuses, setStatuses] = useState<Record<string, StockStatus>>(() =>
    Object.fromEntries(
      aisle.rows.filter((r) => r.mode === 'status').map((r) => [r.item_id, r.status ?? 'ok']),
    ),
  )
  const value = (id: string) => Number((counts[id] ?? '0').replace(',', '.'))
  const step = (row: StockRow, direction: 1 | -1) =>
    setCounts((all) => {
      const now = Number.isFinite(value(row.item_id)) ? value(row.item_id) : 0
      return { ...all, [row.item_id]: String(Math.max(0, now + direction * row.step)) }
    })
  const save = useMutation({
    mutationFn: () => {
      const changedCounts: Record<string, number> = {}
      const changedStatuses: Record<string, StockStatus> = {}
      for (const row of aisle.rows) {
        if (row.mode === 'counted') {
          const counted = value(row.item_id)
          if (Number.isFinite(counted) && Math.abs(counted - (row.level ?? 0)) > 0.01)
            changedCounts[row.item_id] = counted
        } else if (statuses[row.item_id] && statuses[row.item_id] !== row.status) {
          changedStatuses[row.item_id] = statuses[row.item_id] as StockStatus
        }
      }
      return checkAisle({
        category: aisle.category,
        counts: changedCounts,
        statuses: changedStatuses,
      })
    },
    onSuccess: async () => {
      await refresh()
      onDone()
    },
  })
  return (
    <div className="stack pantry-check">
      <ul className="list-rows">
        {aisle.rows.map((row) => (
          <li key={row.item_id} className="list-row stock-row">
            <span className="what">
              <span>{row.name}</span>
            </span>
            {row.mode === 'counted' ? (
              <span className="stepper">
                <button
                  type="button"
                  aria-label={t('stock.less', { name: row.name })}
                  onClick={() => step(row, -1)}
                >
                  −
                </button>
                <input
                  inputMode="decimal"
                  aria-label={t('stock.amountOf', { name: row.name, unit: row.base_unit })}
                  value={counts[row.item_id] ?? ''}
                  onChange={(e) => setCounts((all) => ({ ...all, [row.item_id]: e.target.value }))}
                />
                <small>{row.base_unit}</small>
                <button
                  type="button"
                  aria-label={t('stock.more', { name: row.name })}
                  onClick={() => step(row, 1)}
                >
                  +
                </button>
              </span>
            ) : (
              <span className="row" role="group" aria-label={row.name}>
                {STATUSES.map((s) => (
                  <button
                    key={s}
                    type="button"
                    className={`chip status ${s}`}
                    aria-pressed={statuses[row.item_id] === s}
                    onClick={() => setStatuses((all) => ({ ...all, [row.item_id]: s }))}
                  >
                    {t(`stock.status.${s}`)}
                  </button>
                ))}
              </span>
            )}
          </li>
        ))}
      </ul>
      <ErrorMessage error={save.error} />
      <div className="row spread">
        <button type="button" onClick={onDone}>
          {t('common.cancel')}
        </button>
        <button
          type="button"
          className="primary"
          disabled={save.isPending}
          aria-label={t('stock.markChecked', { aisle: name })}
          onClick={() => save.mutate()}
        >
          {t('stock.checked')}
        </button>
      </div>
    </div>
  )
}
