import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate } from 'react-router'
import { api, call, type Me, type Schemas } from '../../api/client'
import { ErrorMessage } from '../../components/ErrorMessage'
import { Field, SelectField, Toggle } from '../../components/Field'
import { LanguageSelect } from '../../components/LanguageSelect'
import { timeZones } from '../../i18n/format'
import { useInstallPrompt } from '../../pwa/install'
import { signedIn, signedOut, useMe } from '../auth/session'
import { ConnectorSettings } from './ConnectorSettings'
import { PushSettings } from './PushSettings'

export function SettingsPage() {
  const { t } = useTranslation()
  const me = useMe().data
  if (!me) return null
  return (
    <section className="stack">
      <h1>{t('settings.title')}</h1>
      <nav className="stack links">
        <Link to="/targets">{t('settings.targets')}</Link>
        <Link to="/foods">{t('settings.foods')}</Link>
        <Link to="/recipes">{t('settings.recipes')}</Link>
      </nav>
      <AccountSettings me={me} />
      <StartScreenSetting me={me} />
      <SharingSettings me={me} />
      <h2>{t('settings.notifications')}</h2>
      <PushSettings me={me} />
      <ConnectorSettings />
      <InstallSettings />
      <PasswordSettings />
      <div className="row spread">
        <Link to="/about">{t('settings.about')}</Link>
        <LogoutButton />
      </div>
    </section>
  )
}

function useUpdateMe() {
  const client = useQueryClient()
  const patchUser = useMutation({
    mutationFn: (body: Schemas['MePatch']) => call(api.PATCH('/api/me', { body })),
    onSuccess: (me) => signedIn(client, me),
  })
  const patchProfile = useMutation({
    mutationFn: (body: Schemas['ProfilePatch']) => call(api.PATCH('/api/me/profile', { body })),
    onSuccess: (me) => signedIn(client, me),
  })
  return { patchUser, patchProfile }
}

function AccountSettings({ me }: { me: Me }) {
  const { t } = useTranslation()
  const { patchUser } = useUpdateMe()
  const [name, setName] = useState(me.user.display_name)
  function submit(e: FormEvent) {
    e.preventDefault()
    patchUser.mutate({ display_name: name })
  }
  return (
    <>
      <h2>{t('settings.account')}</h2>
      <form onSubmit={submit} className="row">
        <Field
          label={t('settings.displayName')}
          value={name}
          maxLength={60}
          required
          onChange={(e) => setName(e.target.value)}
        />
        <button type="submit" disabled={patchUser.isPending || name === me.user.display_name}>
          {t('common.save')}
        </button>
      </form>
      <LanguageSelect
        value={me.user.language}
        disabled={patchUser.isPending}
        onChange={(language) => patchUser.mutate({ language })}
      />
      <SelectField
        label={t('settings.timeZone')}
        value={me.user.time_zone}
        options={timeZones().map((z) => ({ value: z, label: z }))}
        disabled={patchUser.isPending}
        onChange={(time_zone) => patchUser.mutate({ time_zone })}
      />
      <ErrorMessage error={patchUser.error} />
    </>
  )
}

function SharingSettings({ me }: { me: Me }) {
  const { t } = useTranslation()
  const { patchProfile } = useUpdateMe()
  const p = me.profile
  return (
    <>
      <h2>{t('settings.privacy')}</h2>
      <p className="muted">{t('settings.privacyIntro')}</p>
      <Toggle
        label={t('settings.showWorkouts')}
        checked={p.show_workouts}
        disabled={patchProfile.isPending}
        onChange={(v) => patchProfile.mutate({ show_workouts: v })}
      />
      <Toggle
        label={t('settings.showBody')}
        checked={p.show_body}
        disabled={patchProfile.isPending}
        onChange={(v) => patchProfile.mutate({ show_body: v })}
      />
      <Toggle
        label={t('settings.shareAi')}
        checked={p.share_ai_usage}
        disabled={patchProfile.isPending}
        onChange={(v) => patchProfile.mutate({ share_ai_usage: v })}
      />
      <ErrorMessage error={patchProfile.error} />
    </>
  )
}

function StartScreenSetting({ me }: { me: Me }) {
  const { t } = useTranslation()
  const { patchProfile } = useUpdateMe()
  return (
    <SelectField
      label={t('settings.startScreen')}
      value={me.profile.start_screen}
      options={[
        { value: 'today', label: t('settings.startToday') },
        { value: 'list', label: t('settings.startList') },
      ]}
      disabled={patchProfile.isPending}
      onChange={(v) => patchProfile.mutate({ start_screen: v as 'today' | 'list' })}
    />
  )
}

function InstallSettings() {
  const { t } = useTranslation()
  const prompt = useInstallPrompt()
  return (
    <>
      <h2>{t('settings.install.title')}</h2>
      {prompt.installed ? (
        <p className="muted">{t('settings.install.installed')}</p>
      ) : prompt.available ? (
        <button type="button" className="primary" onClick={() => void prompt.install()}>
          {t('settings.install.button')}
        </button>
      ) : (
        <p className="muted">{t('settings.install.hint')}</p>
      )}
    </>
  )
}

function PasswordSettings() {
  const { t } = useTranslation()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const change = useMutation({
    mutationFn: () =>
      call(
        api.POST('/api/auth/password', {
          body: { current_password: current, new_password: next },
        }),
      ),
    onSuccess: () => {
      setCurrent('')
      setNext('')
    },
  })
  function submit(e: FormEvent) {
    e.preventDefault()
    change.mutate()
  }
  return (
    <form onSubmit={submit} className="stack">
      <h2>{t('settings.password.title')}</h2>
      <Field
        label={t('settings.password.current')}
        type="password"
        autoComplete="current-password"
        required
        value={current}
        onChange={(e) => setCurrent(e.target.value)}
      />
      <Field
        label={t('settings.password.new')}
        type="password"
        autoComplete="new-password"
        required
        minLength={10}
        value={next}
        onChange={(e) => setNext(e.target.value)}
      />
      <ErrorMessage error={change.error} />
      {change.isSuccess ? <p role="status">{t('settings.password.changed')}</p> : null}
      <button type="submit" disabled={change.isPending}>
        {t('settings.password.submit')}
      </button>
    </form>
  )
}

function LogoutButton() {
  const { t } = useTranslation()
  const client = useQueryClient()
  const navigate = useNavigate()
  const logout = useMutation({
    mutationFn: () => call(api.POST('/api/auth/logout')),
    onSettled: () => {
      signedOut(client)
      void navigate('/login', { replace: true })
    },
  })
  return (
    <button type="button" onClick={() => logout.mutate()} disabled={logout.isPending}>
      {t('settings.logout')}
    </button>
  )
}
