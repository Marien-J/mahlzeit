import { useMutation } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { ApiError } from '../../api/client'
import { ErrorMessage } from '../../components/ErrorMessage'
import { Field, SelectField } from '../../components/Field'
import { Sheet } from '../../components/Sheet'
import { todayIn } from '../../lib/dates'
import { uuid7 } from '../../lib/ids'
import { useMe } from '../auth/session'
import {
  createItem,
  draftToItemIn,
  lookupBarcode,
  useItemSearch,
  type Item,
} from '../catalogue/api'
import { storeName } from '../list/model'
import { useListQuery } from '../list/sync'
import { Scanner } from '../log/Scanner'
import { money, priceCents, recordPurchase, useRefreshStock } from './api'

type Line = { key: string; item_id: string | null; text: string; quantity: string; price: string }

const RESULTS = 8

/** A purchase by hand or by barcode, for what never was on the list. */
export function PurchaseSheet({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation()
  const me = useMe().data
  const household = me?.household.id ?? ''
  const today = me ? todayIn(me.user.time_zone) : ''
  const stores = useListQuery(household).data?.stores ?? []
  const refresh = useRefreshStock()
  const [id] = useState(() => uuid7())
  const [storeId, setStoreId] = useState('')
  const [day, setDay] = useState(today)
  const [lines, setLines] = useState<Line[]>([])
  const [query, setQuery] = useState('')
  const [scanning, setScanning] = useState(false)
  const search = useItemSearch(query.trim())

  const add = (line: Omit<Line, 'key' | 'quantity' | 'price'>) => {
    setLines((all) => [...all, { ...line, key: uuid7(), quantity: '', price: '' }])
    setQuery('')
  }
  const addItem = (item: Item) => add({ item_id: item.id, text: item.name })
  const edit = (key: string, change: Partial<Line>) =>
    setLines((all) => all.map((l) => (l.key === key ? { ...l, ...change } : l)))

  const scan = useMutation({
    mutationFn: async (code: string) => {
      try {
        const found = await lookupBarcode(code)
        if (found.item) return addItem(found.item)
        if (found.draft) return addItem(await createItem(draftToItemIn(found.draft)))
      } catch (err) {
        if (!(err instanceof ApiError) || err.code !== 'off_unavailable') throw err
      }
      add({ item_id: null, text: code }) // unknown: a free-text line to name by hand
    },
    onSettled: () => setScanning(false),
  })

  const prices = lines.map((l) => priceCents(l.price))
  const badPrice = prices.some((p) => Number.isNaN(p))
  const total = prices.reduce<number>((sum, p) => sum + (p && !Number.isNaN(p) ? p : 0), 0)
  const save = useMutation({
    mutationFn: () =>
      recordPurchase({
        id,
        store_id: storeId || null,
        day,
        lines: lines.map((l, n) => ({
          item_id: l.item_id,
          text: l.text.trim() || null,
          quantity: l.quantity.trim() || null,
          price_cents: prices[n] ?? null,
        })),
      }),
    onSuccess: async () => {
      await refresh()
      onClose()
    },
  })
  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (lines.length && !badPrice) save.mutate()
  }

  return (
    <Sheet title={t('purchase.title')} onClose={onClose}>
      <form className="stack bought" onSubmit={submit}>
        <div className="row">
          <SelectField
            label={t('list.store')}
            value={storeId}
            options={[
              { value: '', label: t('list.anyStore') },
              ...stores.map((s) => ({ value: s.id, label: storeName(t, s) })),
            ]}
            onChange={setStoreId}
          />
          <label className="field">
            <span>{t('bought.day')}</span>
            <input type="date" value={day} max={today} onChange={(e) => setDay(e.target.value)} />
          </label>
        </div>

        {lines.length ? (
          <ul className="bought-lines">
            {lines.map((l) => (
              <li key={l.key}>
                {l.item_id ? (
                  <span className="what">{l.text}</span>
                ) : (
                  <input
                    aria-label={t('purchase.textOf')}
                    value={l.text}
                    maxLength={120}
                    onChange={(e) => edit(l.key, { text: e.target.value })}
                  />
                )}
                <input
                  aria-label={t('bought.quantityOf', { text: l.text })}
                  placeholder={t('list.quantity')}
                  value={l.quantity}
                  maxLength={40}
                  onChange={(e) => edit(l.key, { quantity: e.target.value })}
                />
                <input
                  aria-label={t('bought.priceOf', { text: l.text })}
                  placeholder={t('bought.price')}
                  inputMode="decimal"
                  value={l.price}
                  onChange={(e) => edit(l.key, { price: e.target.value })}
                />
                <button
                  type="button"
                  className="icon"
                  aria-label={t('purchase.removeLine', { text: l.text })}
                  onClick={() => setLines((all) => all.filter((x) => x.key !== l.key))}
                >
                  ×
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">{t('purchase.intro')}</p>
        )}

        {scanning ? (
          <div className="stack">
            <Scanner onCode={(code) => scan.mutate(code)} />
            {scan.isPending ? <p className="muted">{t('scan.lookingUp')}</p> : null}
          </div>
        ) : (
          <div className="stack">
            <div className="row">
              <Field
                label={t('purchase.search')}
                type="search"
                autoComplete="off"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
              <button type="button" onClick={() => setScanning(true)}>
                {t('purchase.scan')}
              </button>
            </div>
            {query.trim() ? (
              <ul className="list results">
                {(search.data ?? []).slice(0, RESULTS).map((item) => (
                  <li key={item.id}>
                    <button type="button" className="result" onClick={() => addItem(item)}>
                      <span>
                        {item.name}
                        {item.brand ? <small className="muted"> · {item.brand}</small> : null}
                      </span>
                    </button>
                  </li>
                ))}
                <li>
                  <button
                    type="button"
                    className="result"
                    onClick={() => add({ item_id: null, text: query.trim() })}
                  >
                    {t('purchase.asText', { text: query.trim() })}
                  </button>
                </li>
              </ul>
            ) : null}
          </div>
        )}

        {badPrice ? <p className="error">{t('errors.price_invalid')}</p> : null}
        {total > 0 ? <p className="muted">{t('bought.total', { total: money(total) })}</p> : null}
        <ErrorMessage error={scan.error ?? save.error} />
        <div className="row spread">
          <button type="button" onClick={onClose}>
            {t('common.cancel')}
          </button>
          <button
            type="submit"
            className="primary"
            disabled={save.isPending || badPrice || lines.length === 0}
          >
            {t('purchase.save')}
          </button>
        </div>
      </form>
    </Sheet>
  )
}
