import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api, call } from '../../api/client'
import { ErrorMessage } from '../../components/ErrorMessage'
import { Sheet } from '../../components/Sheet'
import { hhmm } from '../../lib/dates'
import { useRecipes } from '../catalogue/api'
import { respondToOffer, type Offer } from './api'

/** Answer an offer with a different meal for the same slot: one of my own plans, a recipe, or
 * just a name. */
export function CounterSheet({ offer, onClose }: { offer: Offer; onClose: () => void }) {
  const { t } = useTranslation()
  const client = useQueryClient()
  const day = useQuery({
    queryKey: ['day', offer.day],
    queryFn: () => call(api.GET('/api/days/{day_}', { params: { path: { day_: offer.day } } })),
  })
  const recipes = useRecipes('recipe')
  const [recipeId, setRecipeId] = useState('')
  const [name, setName] = useState('')
  const mine = (day.data?.people.find((p) => p.is_me)?.entries ?? []).filter(
    (e) => e.slot === offer.slot && e.state === 'planned' && !e.joint,
  )
  const send = useMutation({
    mutationFn: (body: Parameters<typeof respondToOffer>[1]) => respondToOffer(offer.id, body),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ['offers'] })
      await client.invalidateQueries({ queryKey: ['day'] })
      await client.invalidateQueries({ queryKey: ['plan'] })
      onClose()
    },
  })
  const fresh = recipeId !== '' || name.trim() !== ''
  return (
    <Sheet title={t('offers.counterTitle', { name: offer.from_name })} onClose={onClose}>
      <div className="stack">
        {mine.length ? (
          <>
            <h3>{t('offers.myPlans')}</h3>
            <ul className="list results">
              {mine.map((e) => (
                <li key={e.id}>
                  <button
                    type="button"
                    className="result"
                    disabled={send.isPending}
                    onClick={() => send.mutate({ action: 'counter', counter_entry_id: e.id })}
                  >
                    <span>{e.name || e.components.map((c) => c.name).join(', ')}</span>
                    <small className="muted">{hhmm(e.at)}</small>
                  </button>
                </li>
              ))}
            </ul>
          </>
        ) : null}
        <h3>{t('offers.somethingElse')}</h3>
        <label className="field">
          <span>{t('offers.recipe')}</span>
          <select value={recipeId} onChange={(e) => setRecipeId(e.target.value)}>
            <option value="">–</option>
            {(recipes.data ?? []).map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>{t('offers.orName')}</span>
          <input value={name} maxLength={120} onChange={(e) => setName(e.target.value)} />
        </label>
        <ErrorMessage error={send.error} />
        <button
          type="button"
          className="primary"
          disabled={!fresh || send.isPending}
          onClick={() =>
            send.mutate({
              action: 'counter',
              counter_meal: {
                name: recipeId ? null : name.trim(),
                recipe_id: recipeId || null,
                portions: 2,
                components: [],
              },
            })
          }
        >
          {t('offers.suggest')}
        </button>
      </div>
    </Sheet>
  )
}
