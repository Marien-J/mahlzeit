import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { api, call, type Me } from '../../api/client'
import { ErrorMessage } from '../../components/ErrorMessage'
import { Toggle } from '../../components/Field'
import { currentSubscription, disablePush, enablePush, pushSupported } from '../../pwa/push'
import { signedIn } from '../auth/session'

const pushKey = ['push'] as const

export function PushSettings({ me }: { me: Me }) {
  const { t } = useTranslation()
  const client = useQueryClient()
  const status = useQuery({ queryKey: pushKey, queryFn: () => call(api.GET('/api/push')) })
  const device = useQuery({
    queryKey: [...pushKey, 'device'],
    queryFn: async () => (await currentSubscription()) !== null,
    enabled: pushSupported(),
  })
  const refresh = () => void client.invalidateQueries({ queryKey: pushKey })
  const toggle = useMutation({
    mutationFn: async (on: boolean) => {
      if (!on) return disablePush()
      const key = status.data?.public_key
      if (!key) return
      const result = await enablePush(key)
      if (result === 'denied') throw new Error('denied')
    },
    onSettled: refresh,
  })
  const test = useMutation({ mutationFn: () => call(api.POST('/api/push/test')) })
  const offers = useMutation({
    mutationFn: (push_offers: boolean) =>
      call(api.PATCH('/api/me/profile', { body: { push_offers } })),
    onSuccess: (data) => signedIn(client, data),
  })

  if (!pushSupported()) return <p className="muted">{t('settings.push.unsupported')}</p>
  if (status.data && !status.data.configured)
    return <p className="muted">{t('settings.push.notConfigured')}</p>
  const denied = typeof Notification !== 'undefined' && Notification.permission === 'denied'
  const on = device.data === true

  return (
    <div className="stack">
      {denied ? <p className="error">{t('settings.push.denied')}</p> : null}
      <button
        type="button"
        className={on ? undefined : 'primary'}
        disabled={toggle.isPending || denied || !status.data}
        onClick={() => toggle.mutate(!on)}
      >
        {on ? t('settings.push.disable') : t('settings.push.enable')}
      </button>
      {status.data && status.data.devices > 0 ? (
        <p className="muted">{t('settings.push.devices', { count: status.data.devices })}</p>
      ) : null}
      {on ? (
        <button type="button" onClick={() => test.mutate()} disabled={test.isPending}>
          {t('settings.push.test')}
        </button>
      ) : null}
      {test.isSuccess ? <p role="status">{t('settings.push.testSent')}</p> : null}
      <Toggle
        label={t('settings.push.offers')}
        checked={me.profile.push_offers}
        disabled={offers.isPending}
        onChange={(v) => offers.mutate(v)}
      />
      <ErrorMessage
        error={
          toggle.error && !(toggle.error.message === 'denied')
            ? toggle.error
            : (test.error ?? offers.error)
        }
      />
    </div>
  )
}
