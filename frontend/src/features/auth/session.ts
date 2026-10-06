import { useQuery, type QueryClient } from '@tanstack/react-query'
import { ApiError, api, call, setCsrfToken, type Me } from '../../api/client'
import { setLanguage } from '../../i18n'
import { forgetOfflineList } from '../list/sync'

export const meKey = ['me'] as const
const CACHE_KEY = 'mahlzeit.me'

/** The last signed-in user on this device, shown while offline. Holds no secrets. */
function cachedMe(): Me | undefined {
  try {
    const raw = localStorage.getItem(CACHE_KEY)
    return raw
      ? ({ ...(JSON.parse(raw) as Omit<Me, 'csrf_token'>), csrf_token: '' } as Me)
      : undefined
  } catch {
    return undefined
  }
}

function rememberMe(me: Me | null): void {
  try {
    if (me) {
      const { csrf_token, ...rest } = me
      localStorage.setItem(CACHE_KEY, JSON.stringify(rest))
    } else localStorage.removeItem(CACHE_KEY)
  } catch {
    // storage unavailable: offline start just shows the loading state
  }
}

/** Remember the CSRF token and follow the user's language. */
export function applyMe(me: Me): void {
  setCsrfToken(me.csrf_token)
  rememberMe(me)
  void setLanguage(me.user.language)
}

export async function fetchMe(): Promise<Me | null> {
  try {
    const me = await call(api.GET('/api/auth/me'))
    applyMe(me)
    return me
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      setCsrfToken(null)
      rememberMe(null)
      return null
    }
    throw err
  }
}

/** The signed-in user, or null. Offline, the last known user stands in until the server answers. */
export function useMe() {
  return useQuery({
    queryKey: meKey,
    queryFn: fetchMe,
    staleTime: 60_000,
    placeholderData: cachedMe,
  })
}

export function signedIn(client: QueryClient, me: Me): void {
  applyMe(me)
  client.setQueryData(meKey, me)
}

export function signedOut(client: QueryClient): void {
  setCsrfToken(null)
  rememberMe(null)
  forgetOfflineList()
  client.clear()
  client.setQueryData(meKey, null)
}
