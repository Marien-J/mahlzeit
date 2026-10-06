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
      <h2>{t('about.data')}</h2>
      <p className="muted">
        {t('about.bls')}{' '}
        <a href="https://doi.org/10.25826/Data20251217-134202-0" target="_blank" rel="noreferrer">
          {t('about.blsLink')}
        </a>
      </p>
      <p className="muted">
        {t('about.off')}{' '}
        <a href="https://world.openfoodfacts.org" target="_blank" rel="noreferrer">
          {t('about.offLink')}
        </a>
      </p>
      <Link to="/settings">{t('common.back')}</Link>
    </section>
  )
}
