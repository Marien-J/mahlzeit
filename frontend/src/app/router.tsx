import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Navigate, Outlet, createBrowserRouter, useLocation } from 'react-router'
import { OfflineBanner } from '../components/OfflineBanner'
import { JoinPage } from '../features/auth/JoinPage'
import { LoginPage } from '../features/auth/LoginPage'
import { ForgotPage, ResetPage } from '../features/auth/PasswordPages'
import { useMe } from '../features/auth/session'
import { DayPage } from '../features/day/DayPage'
import { ListPage } from '../features/list/ListPage'
import { PlanPage } from '../features/plan/PlanPage'
import { Shell } from './Shell'

function Root() {
  return (
    <>
      <OfflineBanner />
      <Outlet />
    </>
  )
}

const OPENED = 'mahlzeit.opened'

/** Tests start a fresh app per render. */
export function resetOpening(): void {
  try {
    sessionStorage.removeItem(OPENED)
  } catch {
    // no storage
  }
}

/** Today, or the list for people who chose to open on it: only on the first screen of a visit. */
function Home() {
  const me = useMe().data
  const [toList] = useState(() => {
    try {
      const first = sessionStorage.getItem(OPENED) === null
      sessionStorage.setItem(OPENED, '1')
      return first && me?.profile.start_screen === 'list'
    } catch {
      return false
    }
  })
  return toList ? <Navigate to="/list" replace /> : <DayPage />
}

function RequireAuth() {
  const { t } = useTranslation()
  const me = useMe()
  const location = useLocation()
  if (me.isPending && !me.data) return <p className="center muted">{t('app.loading')}</p>
  if (me.isError && !me.data)
    return (
      <div className="center stack">
        <p>{t('app.loadFailed')}</p>
        <button type="button" onClick={() => void me.refetch()}>
          {t('app.retry')}
        </button>
      </div>
    )
  if (!me.data) {
    const next = location.pathname === '/' ? '' : `?next=${encodeURIComponent(location.pathname)}`
    return <Navigate to={`/login${next}`} replace />
  }
  return <Shell me={me.data} />
}

export const routes = [
  {
    element: <Root />,
    children: [
      { path: '/login', element: <LoginPage /> },
      { path: '/join', element: <JoinPage /> },
      { path: '/join/:token', element: <JoinPage /> },
      { path: '/forgot', element: <ForgotPage /> },
      { path: '/reset/:token', element: <ResetPage /> },
      {
        element: <RequireAuth />,
        children: [
          { path: '/', element: <Home /> },
          { path: '/day/:day', element: <DayPage /> },
          { path: '/plan', element: <PlanPage /> },
          { path: '/list', element: <ListPage /> },
          {
            path: '/add',
            lazy: () => import('../features/log/AddPage').then((m) => ({ Component: m.AddPage })),
          },
          {
            path: '/recipes',
            lazy: () =>
              import('../features/recipes/RecipesPage').then((m) => ({
                Component: m.RecipesPage,
              })),
          },
          {
            path: '/foods',
            lazy: () =>
              import('../features/catalogue/FoodsPage').then((m) => ({ Component: m.FoodsPage })),
          },
          {
            path: '/targets',
            lazy: () =>
              import('../features/targets/TargetsPage').then((m) => ({ Component: m.TargetsPage })),
          },
          {
            path: '/household',
            lazy: () =>
              import('../features/household/HouseholdPage').then((m) => ({
                Component: m.HouseholdPage,
              })),
          },
          {
            path: '/settings',
            lazy: () =>
              import('../features/settings/SettingsPage').then((m) => ({
                Component: m.SettingsPage,
              })),
          },
          {
            path: '/about',
            lazy: () =>
              import('../features/about/AboutPage').then((m) => ({ Component: m.AboutPage })),
          },
        ],
      },
      { path: '*', element: <Navigate to="/" replace /> },
    ],
  },
]

export function createRouter() {
  return createBrowserRouter(routes)
}
