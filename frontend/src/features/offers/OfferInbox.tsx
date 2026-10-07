import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ErrorMessage } from '../../components/ErrorMessage'
import { formatDate } from '../../i18n/format'
import { dayAsDate } from '../../lib/dates'
import { grams, kcal } from '../../lib/nutrition'
import { respondToOffer, useOffers, withdrawOffer, type Offer } from './api'
import { CounterSheet } from './CounterSheet'

function mealTitle(offer: Offer): string {
  const meal = offer.meal
  if (!meal) return ''
  return meal.name || meal.components.map((c) => c.name).join(', ')
}

function when(offer: Offer, t: (key: string) => string): string {
  return `${t(`slot.${offer.slot}`)}, ${formatDate(dayAsDate(offer.day), { dateStyle: 'medium', timeZone: 'UTC' })}`
}

/** What waits for an answer, and what I offered that is still open. */
export function OfferInbox() {
  const { t } = useTranslation()
  const offers = useOffers()
  const open = offers.data ?? []
  if (open.length === 0) return null
  return (
    <section className="offers stack" aria-label={t('offers.title')}>
      <h2>{t('offers.title')}</h2>
      <ErrorMessage error={offers.error} />
      <ul className="offer-list">
        {open.map((o) => (
          <li key={o.id} data-testid="offer">
            {o.incoming ? <IncomingOffer offer={o} /> : <OutgoingOffer offer={o} />}
          </li>
        ))}
      </ul>
    </section>
  )
}

function useRefreshAfter() {
  const client = useQueryClient()
  return async () => {
    await client.invalidateQueries({ queryKey: ['offers'] })
    await client.invalidateQueries({ queryKey: ['day'] })
    await client.invalidateQueries({ queryKey: ['plan'] })
  }
}

function IncomingOffer({ offer }: { offer: Offer }) {
  const { t } = useTranslation()
  const refresh = useRefreshAfter()
  const [countering, setCountering] = useState(false)
  const answer = useMutation({
    mutationFn: (action: 'accept' | 'decline') => respondToOffer(offer.id, { action }),
    onSuccess: refresh,
  })
  const effect = offer.effect
  const before = effect?.projection_before
  const after = effect?.projection_after
  return (
    <div className="offer-card">
      <p>
        <strong>
          {offer.counter_of_id
            ? t('offers.counterFrom', { name: offer.from_name })
            : t('offers.offerFrom', { name: offer.from_name })}
        </strong>
        <br />
        <span className="muted">{when(offer, t)}</span>
      </p>
      <p>{mealTitle(offer)}</p>
      {effect ? (
        <p className="muted" data-testid="effect">
          {t('offers.yourShare', {
            percent: Math.round(offer.share * 100),
            kcal: kcal(effect.incoming.values.kcal),
            protein: grams(effect.incoming.values.protein),
          })}
          {before?.kcal != null && after?.kcal != null
            ? ` ${t('offers.effect', { before: kcal(before.kcal), after: kcal(after.kcal) })}`
            : ''}
        </p>
      ) : null}
      <ErrorMessage error={answer.error} />
      <div className="row wrap">
        <button
          type="button"
          className="primary"
          disabled={answer.isPending}
          onClick={() => answer.mutate('accept')}
        >
          {t('offers.accept')}
        </button>
        <button type="button" disabled={answer.isPending} onClick={() => setCountering(true)}>
          {t('offers.counter')}
        </button>
        <button type="button" disabled={answer.isPending} onClick={() => answer.mutate('decline')}>
          {t('offers.decline')}
        </button>
      </div>
      {countering ? (
        <CounterSheet
          offer={offer}
          onClose={() => {
            setCountering(false)
          }}
        />
      ) : null}
    </div>
  )
}

function OutgoingOffer({ offer }: { offer: Offer }) {
  const { t } = useTranslation()
  const refresh = useRefreshAfter()
  const withdraw = useMutation({ mutationFn: () => withdrawOffer(offer.id), onSuccess: refresh })
  return (
    <div className="offer-card outgoing">
      <p>
        {t('offers.waitingFor', { name: offer.to_name })}
        <br />
        <span className="muted">
          {mealTitle(offer)} · {when(offer, t)}
        </span>
      </p>
      <ErrorMessage error={withdraw.error} />
      <button type="button" disabled={withdraw.isPending} onClick={() => withdraw.mutate()}>
        {t('offers.withdraw')}
      </button>
    </div>
  )
}
