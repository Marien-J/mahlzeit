import { useQueryClient } from '@tanstack/react-query'
import { useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { NavLink, Outlet } from 'react-router'
import type { Me } from '../api/client'
import { flush } from '../features/list/sync'
import { useWaitingOffers } from '../features/offers/api'
import { useLiveEvents } from '../features/live/live'

export function Shell({ me }: { me: Me }) {
  const { t } = useTranslation()
  const client = useQueryClient()
  const household = me.household.id
  // On every (re)connect, send whatever the list queued while offline.
  const onReady = useCallback(() => void flush(client, household), [client, household])
  useLiveEvents(true, onReady)
  const waiting = useWaitingOffers()
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
          {waiting > 0 ? (
            <span className="count" aria-label={t('nav.offersWaiting', { count: waiting })}>
              {waiting}
            </span>
          ) : null}
        </NavLink>
        <NavLink to="/plan">{t('nav.plan')}</NavLink>
        <NavLink to="/list">{t('nav.list')}</NavLink>
        <NavLink to="/household">{t('nav.household')}</NavLink>
        <NavLink to="/settings">{t('nav.settings')}</NavLink>
      </nav>
    </div>
  )
}
