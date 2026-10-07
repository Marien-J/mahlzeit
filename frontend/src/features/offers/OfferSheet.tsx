import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ErrorMessage } from '../../components/ErrorMessage'
import { Sheet } from '../../components/Sheet'
import { sendOffer } from './api'

const PRESETS = [0.25, 0.5, 0.75]

/** Offer one of my planned meals to the partner, with the share they would eat. */
export function OfferSheet({
  entryId,
  title,
  partner,
  onClose,
}: {
  entryId: string
  title: string
  partner: { id: string; name: string }
  onClose: () => void
}) {
  const { t } = useTranslation()
  const client = useQueryClient()
  const [share, setShare] = useState(0.5)
  const send = useMutation({
    mutationFn: () => sendOffer(entryId, partner.id, share),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ['offers'] })
      await client.invalidateQueries({ queryKey: ['plan'] })
      onClose()
    },
  })
  return (
    <Sheet title={t('offers.offerTitle', { name: partner.name })} onClose={onClose}>
      <div className="stack">
        <p>{title}</p>
        <p className="muted">{t('offers.shareIntro', { name: partner.name })}</p>
        <div
          className="row wrap"
          role="group"
          aria-label={t('offers.theirShare', { name: partner.name })}
        >
          {PRESETS.map((p) => (
            <button
              key={p}
              type="button"
              aria-pressed={share === p}
              className={share === p ? 'chip active' : 'chip'}
              onClick={() => setShare(p)}
            >
              {Math.round(p * 100)} %
            </button>
          ))}
        </div>
        <ErrorMessage error={send.error} />
        <button
          type="button"
          className="primary"
          disabled={send.isPending}
          onClick={() => send.mutate()}
        >
          {t('offers.send')}
        </button>
      </div>
    </Sheet>
  )
}
