import { useQuery } from '@tanstack/react-query'
import { api, call, type Schemas } from '../../api/client'
import { useLiveConnected } from '../live/live'

export type Offer = Schemas['OfferOut']
export type OfferResponse = Schemas['OfferResponseIn']

export const offersKey = ['offers'] as const

/** The open offers to or from me. The badge counts those waiting for my answer. */
export function useOffers() {
  const live = useLiveConnected()
  return useQuery({
    queryKey: offersKey,
    queryFn: () => call(api.GET('/api/offers')),
    // While the event stream is down, ask every 15 seconds.
    refetchInterval: live ? false : 15_000,
  })
}

export function useWaitingOffers(): number {
  return (useOffers().data ?? []).filter((o) => o.incoming).length
}

export function sendOffer(entryId: string, toUserId: string, share: number) {
  return call(api.POST('/api/offers', { body: { entry_id: entryId, to_user_id: toUserId, share } }))
}

export function respondToOffer(id: string, body: OfferResponse) {
  return call(
    api.POST('/api/offers/{offer_id}/respond', { params: { path: { offer_id: id } }, body }),
  )
}

export function withdrawOffer(id: string) {
  return call(api.POST('/api/offers/{offer_id}/withdraw', { params: { path: { offer_id: id } } }))
}
