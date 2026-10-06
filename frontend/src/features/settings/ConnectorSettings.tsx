import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api, call } from '../../api/client'
import { ErrorMessage } from '../../components/ErrorMessage'
import { formatDateTime } from '../../i18n/format'

const key = ['connector'] as const

/** The personal connector URL for Claude. Shown once; a new one replaces the old. */
export function ConnectorSettings() {
  const { t } = useTranslation()
  const client = useQueryClient()
  const status = useQuery({ queryKey: key, queryFn: () => call(api.GET('/api/connector')) })
  const [url, setUrl] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const create = useMutation({
    mutationFn: () => call(api.POST('/api/connector')),
    onSuccess: (data) => {
      setUrl(data.url)
      setCopied(false)
      void client.invalidateQueries({ queryKey: key })
    },
  })
  const revoke = useMutation({
    mutationFn: () => call(api.DELETE('/api/connector')),
    onSuccess: () => {
      setUrl(null)
      void client.invalidateQueries({ queryKey: key })
    },
  })
  const copy = async () => {
    if (!url) return
    try {
      await navigator.clipboard.writeText(url)
      setCopied(true)
    } catch {
      setCopied(false)
    }
  }
  const active = status.data?.active ?? false
  const busy = create.isPending || revoke.isPending
  return (
    <>
      <h2>{t('connector.title')}</h2>
      <p className="muted">{t('connector.intro')}</p>
      {url ? (
        <div className="card stack" data-testid="connector-url">
          <p>
            <strong>{t('connector.onceOnly')}</strong>
          </p>
          <input
            readOnly
            value={url}
            aria-label={t('connector.url')}
            onFocus={(e) => e.target.select()}
          />
          <button type="button" onClick={() => void copy()}>
            {copied ? t('connector.copied') : t('connector.copy')}
          </button>
          <ol className="muted">
            <li>{t('connector.step1')}</li>
            <li>{t('connector.step2')}</li>
            <li>{t('connector.step3')}</li>
          </ol>
        </div>
      ) : null}
      {status.data ? (
        active ? (
          <p className="muted">
            {t('connector.active', { created: formatDateTime(status.data.created_at ?? '') })}{' '}
            {status.data.last_used_at
              ? t('connector.lastUsed', { at: formatDateTime(status.data.last_used_at) })
              : t('connector.neverUsed')}
          </p>
        ) : (
          <p className="muted">{t('connector.inactive')}</p>
        )
      ) : null}
      <div className="row">
        <button
          type="button"
          className={active ? undefined : 'primary'}
          disabled={busy}
          onClick={() => create.mutate()}
        >
          {active ? t('connector.rotate') : t('connector.create')}
        </button>
        {active ? (
          <button type="button" className="danger" disabled={busy} onClick={() => revoke.mutate()}>
            {t('connector.revoke')}
          </button>
        ) : null}
      </div>
      <ErrorMessage error={status.error ?? create.error ?? revoke.error} />
    </>
  )
}
