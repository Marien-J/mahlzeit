import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { useServerConfig } from '../auth/PasswordPages'

export function AboutPage() {
  const { t } = useTranslation()
  const config = useServerConfig()
  return (
    <section className="stack">
      <h1>{t('about.title')}</h1>
      <p>{t('about.version', { version: config.data?.version ?? '…' })}</p>
      <p>{t('about.privacy')}</p>
      <p className="muted">{t('about.attribution')}</p>
      <Link to="/settings">{t('common.back')}</Link>
    </section>
  )
}
