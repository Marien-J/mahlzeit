import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router'
import { api, call } from '../../api/client'
import { ErrorMessage } from '../../components/ErrorMessage'
import { Field } from '../../components/Field'
import { PublicLayout } from './PublicLayout'
import { signedIn, useMe } from './session'

/** Only same-app paths are followed after sign-in. */
export function safeNext(next: string | null): string {
  return next && next.startsWith('/') && !next.startsWith('//') ? next : '/'
}

export function LoginPage() {
  const { t } = useTranslation()
  const client = useQueryClient()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const me = useMe()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const login = useMutation({
    mutationFn: () => call(api.POST('/api/auth/login', { body: { email, password } })),
    onSuccess: (data) => {
      signedIn(client, data)
      void navigate(safeNext(params.get('next')), { replace: true })
    },
  })

  if (me.data) return <Navigate to={safeNext(params.get('next'))} replace />

  function submit(e: FormEvent) {
    e.preventDefault()
    login.mutate()
  }

  return (
    <PublicLayout title={t('login.title')}>
      <form onSubmit={submit} className="stack">
        <Field
          label={t('login.email')}
          type="email"
          autoComplete="username"
          inputMode="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <Field
          label={t('login.password')}
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <ErrorMessage error={login.error} />
        <button type="submit" className="primary" disabled={login.isPending}>
          {t('login.submit')}
        </button>
      </form>
      <nav className="links">
        <Link to="/forgot">{t('login.forgot')}</Link>
        <Link to="/join">{t('login.join')}</Link>
      </nav>
      <p className="muted">{t('login.noAccount')}</p>
    </PublicLayout>
  )
}
