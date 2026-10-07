import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { ErrorMessage } from '../../components/ErrorMessage'
import { addDays, todayIn } from '../../lib/dates'
import { useMe } from '../auth/session'
import { amountText, money, useStockReport } from './api'

const PERIODS = [7, 30, 90] as const

/** Purchased versus logged per item: where the food went, and what it cost where prices exist. */
export function ReportPage() {
  const { t } = useTranslation()
  const me = useMe().data
  const [days, setDays] = useState<(typeof PERIODS)[number]>(30)
  const end = me ? todayIn(me.user.time_zone) : ''
  const start = end ? addDays(end, 1 - days) : ''
  const report = useStockReport(start, end)
  if (!me) return null
  const signed = (value: number, unit: 'g' | 'ml') =>
    `${value < 0 ? '−' : '+'}${amountText(Math.abs(value), unit)}`
  return (
    <section className="stack report">
      <header className="row spread">
        <h1>{t('report.title')}</h1>
        <Link to="/stock">{t('stock.title')}</Link>
      </header>
      <div className="chips" role="group" aria-label={t('report.period')}>
        {PERIODS.map((p) => (
          <button
            key={p}
            type="button"
            className={p === days ? 'chip active' : 'chip'}
            aria-pressed={p === days}
            onClick={() => setDays(p)}
          >
            {t('report.days', { count: p })}
          </button>
        ))}
      </div>
      <ErrorMessage error={report.error} />
      {report.data ? (
        <>
          {report.data.spend_cents > 0 ? (
            <p>{t('report.spend', { total: money(report.data.spend_cents) })}</p>
          ) : null}
          {report.data.rows.length === 0 ? <p className="muted">{t('report.empty')}</p> : null}
          <ul className="report-rows">
            {report.data.rows.map((r) => (
              <li key={r.item_id} aria-label={r.name}>
                <div className="row spread">
                  <strong>{r.name}</strong>
                  {r.spend_cents != null ? (
                    <span className="muted">{money(r.spend_cents)}</span>
                  ) : null}
                </div>
                <dl>
                  <div>
                    <dt>{t('report.purchased')}</dt>
                    <dd>{amountText(r.purchased, r.base_unit)}</dd>
                  </div>
                  <div>
                    <dt>{t('report.logged')}</dt>
                    <dd>{amountText(r.logged, r.base_unit)}</dd>
                  </div>
                  {r.wasted ? (
                    <div>
                      <dt>{t('report.wasted')}</dt>
                      <dd>{amountText(r.wasted, r.base_unit)}</dd>
                    </div>
                  ) : null}
                  {r.corrected ? (
                    <div>
                      <dt>{t('report.corrected')}</dt>
                      <dd>{signed(r.corrected, r.base_unit)}</dd>
                    </div>
                  ) : null}
                  {r.shortfall ? (
                    <div>
                      <dt>{t('report.shortfall')}</dt>
                      <dd>{amountText(r.shortfall, r.base_unit)}</dd>
                    </div>
                  ) : null}
                  {r.level != null ? (
                    <div>
                      <dt>{t('report.left')}</dt>
                      <dd>{amountText(r.level, r.base_unit)}</dd>
                    </div>
                  ) : null}
                </dl>
              </li>
            ))}
          </ul>
          <p className="muted">{t('report.note')}</p>
        </>
      ) : (
        <p className="muted">{t('app.loading')}</p>
      )}
    </section>
  )
}
