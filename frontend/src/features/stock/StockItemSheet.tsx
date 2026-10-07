import { useMutation } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { ErrorMessage } from '../../components/ErrorMessage'
import { Field, Toggle } from '../../components/Field'
import { Sheet } from '../../components/Sheet'
import { formatDate } from '../../i18n/format'
import {
  adjustStock,
  amountText,
  setTrackingMode,
  useItemStock,
  useRefreshStock,
  type StockRow,
} from './api'

const number = (text: string) => Number(text.replace(',', '.'))

/** One item: fix what is there, write off what was thrown away, choose how it is tracked. */
export function StockItemSheet({ row, onClose }: { row: StockRow; onClose: () => void }) {
  const { t } = useTranslation()
  const detail = useItemStock(row.item_id)
  const refresh = useRefreshStock()
  const current = detail.data?.stock ?? row
  const [count, setCount] = useState('')
  const [waste, setWaste] = useState('')
  const adjust = useMutation({
    mutationFn: (body: Parameters<typeof adjustStock>[1]) => adjustStock(row.item_id, body),
    onSuccess: async () => {
      setCount('')
      setWaste('')
      await refresh()
    },
  })
  const mode = useMutation({
    mutationFn: (statusOnly: boolean) =>
      setTrackingMode(row.item_id, statusOnly ? 'status' : 'counted'),
    onSuccess: refresh,
  })
  const submitCount = (e: FormEvent) => {
    e.preventDefault()
    if (count.trim()) adjust.mutate({ count: number(count) })
  }
  const submitWaste = (e: FormEvent) => {
    e.preventDefault()
    if (waste.trim()) adjust.mutate({ waste: number(waste) })
  }
  const unit = current.base_unit
  return (
    <Sheet title={current.name} onClose={onClose}>
      <div className="stack">
        <p className="level-now">
          {current.mode === 'counted'
            ? t('stock.levelNow', { amount: amountText(current.level ?? 0, unit) })
            : t('stock.statusNow', { status: t(`stock.status.${current.status ?? 'ok'}`) })}
        </p>
        {current.mode === 'counted' ? (
          <>
            <form className="row" onSubmit={submitCount}>
              <Field
                label={t('stock.countNow', { unit })}
                inputMode="decimal"
                value={count}
                onChange={(e) => setCount(e.target.value)}
              />
              <button type="submit" disabled={adjust.isPending || !count.trim()}>
                {t('common.save')}
              </button>
            </form>
            <form className="row" onSubmit={submitWaste}>
              <Field
                label={t('stock.thrownAway', { unit })}
                inputMode="decimal"
                value={waste}
                onChange={(e) => setWaste(e.target.value)}
              />
              <button type="submit" disabled={adjust.isPending || !waste.trim()}>
                {t('stock.writeOff')}
              </button>
            </form>
          </>
        ) : null}
        <Toggle
          label={t('stock.statusOnly')}
          checked={current.mode === 'status'}
          disabled={mode.isPending}
          onChange={(on) => mode.mutate(on)}
        />
        <ErrorMessage error={adjust.error ?? mode.error ?? detail.error} />
        {detail.data?.movements.length ? (
          <section className="stack" aria-label={t('stock.history')}>
            <h3>{t('stock.history')}</h3>
            <ul className="list compact movements">
              {detail.data.movements.map((m) => (
                <li key={m.id} className="row spread">
                  <span>{formatDate(`${m.day}T12:00:00Z`, { timeZone: 'UTC' })}</span>
                  <span>
                    {t(`stock.movement.${m.source === 'shortfall' ? m.source : m.reason}`)}
                  </span>
                  <span className={m.amount < 0 ? 'minus' : 'plus'}>
                    {m.amount > 0 ? '+' : '−'}
                    {amountText(Math.abs(m.amount), unit)}
                  </span>
                </li>
              ))}
            </ul>
          </section>
        ) : null}
      </div>
    </Sheet>
  )
}
