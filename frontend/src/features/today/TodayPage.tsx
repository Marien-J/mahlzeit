import { useTranslation } from 'react-i18next'
import { useMe } from '../auth/session'
import { formatDate } from '../../i18n/format'

/** M0 placeholder for the day view: date and greeting. The timeline arrives with tracking (M1). */
export function TodayPage() {
  const { t } = useTranslation()
  const me = useMe().data
  if (!me) return null
  const today = formatDate(new Date(), { dateStyle: 'full', timeZone: me.user.time_zone })
  return (
    <section>
      <p className="muted">{today}</p>
      <h1>{t('today.greeting', { name: me.user.display_name })}</h1>
      <p className="card muted">{t('today.empty')}</p>
    </section>
  )
}
