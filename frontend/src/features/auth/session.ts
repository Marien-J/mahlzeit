import { useQuery, type QueryClient } from '@tanstack/react-query'
import { ApiError, api, call, setCsrfToken, type Me } from '../../api/client'
import { setLanguage } from '../../i18n'

export const meKey = ['me'] as const

/** Remember the CSRF token and follow the user's language. */
export function applyMe(me: Me): void {
  setCsrfToken(me.csrf_token)
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
      return null
    }
    throw err
  }
}

/** The signed-in user, or null. */
export function useMe() {
  return useQuery({ queryKey: meKey, queryFn: fetchMe, staleTime: 60_000 })
}

export function signedIn(client: QueryClient, me: Me): void {
  applyMe(me)
  client.setQueryData(meKey, me)
}

export function signedOut(client: QueryClient): void {
  setCsrfToken(null)
  client.clear()
  client.setQueryData(meKey, null)
}
