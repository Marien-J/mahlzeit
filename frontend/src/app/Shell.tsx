import { useTranslation } from 'react-i18next'
import { NavLink, Outlet } from 'react-router'
import type { Me } from '../api/client'

export function Shell({ me }: { me: Me }) {
  const { t } = useTranslation()
  return (
    <div className="shell">
      <header className="topbar">
        <span className="brand">{t('app.name')}</span>
        <span className="muted">{me.household.name}</span>
      </header>
      <main className="content">
        <Outlet />
      </main>
      <nav className="tabbar" aria-label={t('nav.main')}>
        <NavLink to="/" end>
          {t('nav.today')}
        </NavLink>
        <NavLink to="/household">{t('nav.household')}</NavLink>
        <NavLink to="/settings">{t('nav.settings')}</NavLink>
      </nav>
    </div>
  )
}
