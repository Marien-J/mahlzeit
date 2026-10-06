import { useMutation, useQuery } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router'
import { api, call } from '../../api/client'
import { ErrorMessage } from '../../components/ErrorMessage'
import { Field } from '../../components/Field'
import { PublicLayout } from './PublicLayout'

export function useServerConfig() {
  return useQuery({
    queryKey: ['config'],
    queryFn: () => call(api.GET('/api/config')),
    staleTime: Infinity,
  })
}

export function ForgotPage() {
  const { t } = useTranslation()
  const config = useServerConfig()
  const [email, setEmail] = useState('')
  const request = useMutation({
    mutationFn: () => call(api.POST('/api/auth/password-reset/request', { body: { email } })),
  })

  function submit(e: FormEvent) {
    e.preventDefault()
    request.mutate()
  }

  let body
  if (config.data && !config.data.email_reset) body = <p>{t('forgot.disabled')}</p>
  else if (request.isSuccess) body = <p role="status">{t('forgot.sent')}</p>
  else
    body = (
      <form onSubmit={submit} className="stack">
        <p>{t('forgot.intro')}</p>
        <Field
          label={t('login.email')}
          type="email"
          autoComplete="username"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <ErrorMessage error={request.error} />
        <button type="submit" className="primary" disabled={request.isPending}>
          {t('forgot.submit')}
        </button>
      </form>
    )

  return (
    <PublicLayout title={t('forgot.title')}>
      {body}
      <nav className="links">
        <Link to="/login">{t('common.back')}</Link>
      </nav>
    </PublicLayout>
  )
}

export function ResetPage() {
  const { t } = useTranslation()
  const { token = '' } = useParams()
  const [password, setPassword] = useState('')
  const confirm = useMutation({
    mutationFn: () =>
      call(api.POST('/api/auth/password-reset/confirm', { body: { token, password } })),
  })

  function submit(e: FormEvent) {
    e.preventDefault()
    confirm.mutate()
  }

  return (
    <PublicLayout title={t('reset.title')}>
      {confirm.isSuccess ? (
        <>
          <p role="status">{t('reset.done')}</p>
          <Link to="/login" className="button primary">
            {t('reset.toLogin')}
          </Link>
        </>
      ) : (
        <form onSubmit={submit} className="stack">
          <Field
            label={t('reset.password')}
            type="password"
            autoComplete="new-password"
            required
            minLength={10}
            hint={t('join.passwordHint', { min: 10 })}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <ErrorMessage error={confirm.error} />
          <button type="submit" className="primary" disabled={confirm.isPending}>
            {t('reset.submit')}
          </button>
        </form>
      )}
    </PublicLayout>
  )
}
