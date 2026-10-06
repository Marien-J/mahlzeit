import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate, useParams } from 'react-router'
import { api, call, type Schemas } from '../../api/client'
import { ErrorMessage } from '../../components/ErrorMessage'
import { Field, SelectField } from '../../components/Field'
import { isLanguage, setLanguage, type Language } from '../../i18n'
import { browserTimeZone, formatDateTime, timeZones } from '../../i18n/format'
import { PublicLayout } from './PublicLayout'
import { signedIn, signedOut, useMe } from './session'

const PASSWORD_MIN = 10

/** /join (type a code) and /join/:token (from the link). */
export function JoinPage() {
  const { t } = useTranslation()
  const { token } = useParams()
  const [typed, setTyped] = useState('')
  const [key, setKey] = useState(token ?? '')
  const me = useMe()
  const client = useQueryClient()

  const preview = useQuery({
    queryKey: ['invite', key],
    queryFn: () => call(api.GET('/api/invites/{key}', { params: { path: { key } } })),
    enabled: key.length > 0,
    retry: false,
  })

  if (me.data) {
    return (
      <PublicLayout title={t('join.title')}>
        <p>{t('join.signedIn', { name: me.data.user.display_name })}</p>
        <button
          type="button"
          onClick={async () => {
            await call(api.POST('/api/auth/logout'))
            signedOut(client)
          }}
        >
          {t('join.signOut')}
        </button>
      </PublicLayout>
    )
  }

  if (!key || preview.isError) {
    return (
      <PublicLayout title={t('join.title')}>
        <form
          className="stack"
          onSubmit={(e) => {
            e.preventDefault()
            setKey(typed.trim())
          }}
        >
          <p>{t('join.enterCode')}</p>
          <Field
            label={t('join.code')}
            autoCapitalize="characters"
            autoComplete="off"
            required
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
          />
          <ErrorMessage error={preview.error} />
          <button type="submit" className="primary">
            {t('join.continue')}
          </button>
        </form>
      </PublicLayout>
    )
  }

  if (!preview.data) return <PublicLayout title={t('join.title')}>{t('app.loading')}</PublicLayout>
  return <JoinForm inviteKey={key} invite={preview.data} />
}

function JoinForm({
  inviteKey,
  invite,
}: {
  inviteKey: string
  invite: Schemas['InvitePreviewOut']
}) {
  const { t, i18n } = useTranslation()
  const client = useQueryClient()
  const navigate = useNavigate()
  const [form, setForm] = useState({
    display_name: '',
    email: '',
    password: '',
    household_name: '',
    language: (isLanguage(i18n.language) ? i18n.language : invite.language) as Language,
    time_zone: browserTimeZone(),
  })
  const update = (patch: Partial<typeof form>) => setForm((f) => ({ ...f, ...patch }))
  const accept = useMutation({
    mutationFn: () =>
      call(
        api.POST('/api/invites/accept', {
          body: {
            key: inviteKey,
            ...form,
            household_name: invite.kind === 'household' ? form.household_name || null : null,
          },
        }),
      ),
    onSuccess: (me) => {
      signedIn(client, me)
      void navigate('/', { replace: true })
    },
  })

  if (invite.status !== 'pending') {
    return (
      <PublicLayout title={t('join.title')}>
        <p className="error">{t(`join.status.${invite.status}`)}</p>
      </PublicLayout>
    )
  }

  function submit(e: FormEvent) {
    e.preventDefault()
    accept.mutate()
  }

  return (
    <PublicLayout title={t('join.title')} languageSwitch={false}>
      <p>
        {invite.kind === 'partner'
          ? t('join.partnerInvite', {
              inviter: invite.inviter_name ?? '',
              household: invite.household_name ?? '',
            })
          : t('join.householdInvite')}
      </p>
      <p className="muted">{t('join.expires', { date: formatDateTime(invite.expires_at) })}</p>
      <form onSubmit={submit} className="stack">
        <Field
          label={t('join.displayName')}
          autoComplete="given-name"
          required
          maxLength={60}
          value={form.display_name}
          onChange={(e) => update({ display_name: e.target.value })}
        />
        <Field
          label={t('join.email')}
          type="email"
          autoComplete="username"
          inputMode="email"
          required
          value={form.email}
          onChange={(e) => update({ email: e.target.value })}
        />
        <Field
          label={t('join.password')}
          type="password"
          autoComplete="new-password"
          required
          minLength={PASSWORD_MIN}
          hint={t('join.passwordHint', { min: PASSWORD_MIN })}
          value={form.password}
          onChange={(e) => update({ password: e.target.value })}
        />
        {invite.kind === 'household' ? (
          <Field
            label={t('join.householdName')}
            maxLength={80}
            value={form.household_name}
            onChange={(e) => update({ household_name: e.target.value })}
          />
        ) : null}
        <SelectField
          label={t('common.language')}
          value={form.language}
          options={(['de', 'en', 'nl'] as const).map((l) => ({
            value: l,
            label: t(`languages.${l}`),
          }))}
          onChange={(v) => {
            if (isLanguage(v)) {
              update({ language: v })
              void setLanguage(v)
            }
          }}
        />
        <SelectField
          label={t('join.timeZone')}
          value={form.time_zone}
          options={timeZones().map((z) => ({ value: z, label: z }))}
          onChange={(v) => update({ time_zone: v })}
        />
        <ErrorMessage error={accept.error} />
        <button type="submit" className="primary" disabled={accept.isPending}>
          {t('join.submit')}
        </button>
      </form>
    </PublicLayout>
  )
}
