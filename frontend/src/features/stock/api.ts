import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback } from 'react'
import { api, call, type Schemas } from '../../api/client'
import { formatNumber } from '../../i18n/format'

export type StockRow = Schemas['StockRowOut']
export type StockData = Schemas['StockOut']
export type StockStatus = NonNullable<StockRow['status']>
export type Suggestion = Schemas['SuggestionOut']
export type PurchaseIn = Schemas['PurchaseIn']
export type PurchaseLineIn = Schemas['PurchaseLineIn']
export type Report = Schemas['StockReportOut']

export const stockKey = ['stock'] as const
export const suggestionsKey = ['list', 'suggestions'] as const
export const STATUSES: StockStatus[] = ['ok', 'low', 'out']

export function useStock() {
  return useQuery({ queryKey: stockKey, queryFn: () => call(api.GET('/api/stock')) })
}

export function useItemStock(itemId: string) {
  return useQuery({
    queryKey: [...stockKey, 'item', itemId],
    queryFn: () =>
      call(api.GET('/api/stock/items/{item_id}', { params: { path: { item_id: itemId } } })),
  })
}

export function useStockReport(start: string, end: string) {
  return useQuery({
    queryKey: [...stockKey, 'report', start, end],
    queryFn: () => call(api.GET('/api/stock/report', { params: { query: { start, end } } })),
    placeholderData: (previous) => previous,
  })
}

/** What the list could use; nothing here is ever added by itself. */
export function useSuggestions(enabled = true) {
  return useQuery({
    queryKey: suggestionsKey,
    queryFn: () => call(api.GET('/api/list/suggestions')),
    enabled,
    retry: false,
  })
}

export function recordPurchase(body: PurchaseIn) {
  return call(api.POST('/api/purchases', { body }))
}

export function adjustStock(itemId: string, body: Schemas['StockAdjustIn']) {
  return call(
    api.POST('/api/stock/items/{item_id}/adjust', { params: { path: { item_id: itemId } }, body }),
  )
}

export function setTrackingMode(itemId: string, mode: StockRow['mode'] | null) {
  return call(
    api.PUT('/api/stock/items/{item_id}/mode', {
      params: { path: { item_id: itemId } },
      body: { mode },
    }),
  )
}

export function checkAisle(body: Schemas['PantryCheckIn']) {
  return call(api.POST('/api/stock/checks', { body }))
}

/** After a purchase or a change by hand: stock, the list and its suggestions. */
export function useRefreshStock() {
  const client = useQueryClient()
  return useCallback(
    () =>
      Promise.all([
        client.invalidateQueries({ queryKey: stockKey }),
        client.invalidateQueries({ queryKey: ['list'] }),
        client.invalidateQueries({ queryKey: ['purchases'] }),
      ]),
    [client],
  )
}

/** One tap moves a status-only item along: ok → low → out → ok. */
export function nextStatus(status: StockStatus | null | undefined): StockStatus {
  const at = STATUSES.indexOf(status ?? 'ok')
  return STATUSES[(at + 1) % STATUSES.length] ?? 'ok'
}

/** '850 g', '1,2 kg', '1,5 l': amounts as people say them. */
export function amountText(value: number, unit: 'g' | 'ml'): string {
  if (value >= 1000) {
    const big = unit === 'g' ? 'kg' : 'l'
    return `${formatNumber(value / 1000, { maximumFractionDigits: 2 })} ${big}`
  }
  return `${formatNumber(value, { maximumFractionDigits: value < 10 ? 1 : 0 })} ${unit}`
}

/** '1,99' or '1.99' → 199 cents; empty is no price; anything else is NaN. */
export function priceCents(text: string): number | null {
  const cleaned = text.trim().replace('€', '').trim().replace(',', '.')
  if (!cleaned) return null
  const value = Number(cleaned)
  return Number.isFinite(value) && value >= 0 ? Math.round(value * 100) : Number.NaN
}

export function money(cents: number): string {
  return formatNumber(cents / 100, { style: 'currency', currency: 'EUR' })
}
