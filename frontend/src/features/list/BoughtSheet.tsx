import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { ApiError } from '../../api/client'
import { ErrorMessage } from '../../components/ErrorMessage'
import { SelectField } from '../../components/Field'
import { Sheet } from '../../components/Sheet'
import { uuid7 } from '../../lib/ids'
import { money, priceCents, recordPurchase, useRefreshStock } from '../stock/api'
import { storeName, type ListItem, type Store } from './model'
import { flush, pendingCount } from './sync'

type Line = { quantity: string; price: string }

/**
 * 'Bought': the checked items become one purchase. Pick the store, fix quantities, add prices if
 * you like, confirm. Food goes into stock and the items leave the list. The purchase id is made
 * here once, so tapping Confirm again after a lost answer records it once.
 */
export function BoughtSheet({
  household,
  items,
  stores,
  store,
  today,
  onClose,
  onDone,
}: {
  household: string
  items: ListItem[]
  stores: Store[]
  store: string | null
  today: string
  onClose: () => void
  onDone: (count: number) => void
}) {
  const { t } = useTranslation()
  const client = useQueryClient()
  const refresh = useRefreshStock()
  const [id] = useState(() => uuid7())
  const shared = new Set(items.map((i) => i.store_id))
  const [storeId, setStoreId] = useState<string>(
    store ?? (shared.size === 1 ? ([...shared][0] ?? '') : ''),
  )
  const [day, setDay] = useState(today)
  const [lines, setLines] = useState<Record<string, Line>>(() =>
    Object.fromEntries(items.map((i) => [i.id, { quantity: i.quantity ?? '', price: '' }])),
  )
  const edit = (itemId: string, change: Partial<Line>) =>
    setLines((all) => ({
      ...all,
      [itemId]: { ...(all[itemId] ?? { quantity: '', price: '' }), ...change },
    }))
  const prices = items.map((i) => priceCents(lines[i.id]?.price ?? ''))
  const badPrice = prices.some((p) => Number.isNaN(p))
  const total = prices.reduce<number>((sum, p) => sum + (p && !Number.isNaN(p) ? p : 0), 0)

  const confirm = useMutation({
    mutationFn: async () => {
      // The list changes made here first, so the server knows every item that was bought.
      await flush(client, household)
      if (pendingCount(household) > 0) throw new ApiError(0, 'network')
      return recordPurchase({
        id,
        store_id: storeId || null,
        day,
        lines: items.map((i, n) => ({
          list_item_id: i.id,
          item_id: i.item_id,
          text: i.text,
          quantity: (lines[i.id]?.quantity ?? '').trim() || null,
          price_cents: prices[n] ?? null,
        })),
      })
    },
    onSuccess: async (purchase) => {
      await refresh()
      onDone(purchase.lines.length)
    },
  })

  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (!badPrice) confirm.mutate()
  }

  return (
    <Sheet title={t('bought.title')} onClose={onClose}>
      <form className="stack bought" onSubmit={submit}>
        <p className="muted">{t('bought.intro')}</p>
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
        <ul className="bought-lines">
          {items.map((i) => (
            <li key={i.id}>
              <span className="what">
                {i.text}
                {i.item_id ? <small className="muted">{t('bought.intoStock')}</small> : null}
              </span>
              <input
                aria-label={t('bought.quantityOf', { text: i.text })}
                placeholder={t('list.quantity')}
                value={lines[i.id]?.quantity ?? ''}
                maxLength={40}
                onChange={(e) => edit(i.id, { quantity: e.target.value })}
              />
              <input
                aria-label={t('bought.priceOf', { text: i.text })}
                placeholder={t('bought.price')}
                inputMode="decimal"
                value={lines[i.id]?.price ?? ''}
                onChange={(e) => edit(i.id, { price: e.target.value })}
              />
            </li>
          ))}
        </ul>
        {badPrice ? <p className="error">{t('errors.price_invalid')}</p> : null}
        {total > 0 ? <p className="muted">{t('bought.total', { total: money(total) })}</p> : null}
        <ErrorMessage error={confirm.error} />
        <div className="row spread">
          <button type="button" onClick={onClose}>
            {t('common.cancel')}
          </button>
          <button type="submit" className="primary" disabled={confirm.isPending || badPrice}>
            {t('bought.confirm', { count: items.length })}
          </button>
        </div>
      </form>
    </Sheet>
  )
}
