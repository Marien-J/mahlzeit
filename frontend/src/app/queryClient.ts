import { MutationCache, QueryCache, QueryClient } from '@tanstack/react-query'
import { ApiError } from '../api/client'
import { meKey } from '../features/auth/session'

function isAuthError(err: unknown) {
  return err instanceof ApiError && err.status === 401
}

export function createQueryClient(): QueryClient {
  // A 401 anywhere means the session ended: drop the user so the router shows sign-in.
  const onError = (err: unknown) => {
    if (isAuthError(err)) client.setQueryData(meKey, null)
  }
  const client: QueryClient = new QueryClient({
    queryCache: new QueryCache({ onError }),
    mutationCache: new MutationCache({ onError }),
    defaultOptions: {
      queries: {
        retry: (count, err) =>
          !(err instanceof ApiError && err.status >= 400 && err.status < 500) && count < 2,
        refetchOnWindowFocus: true,
      },
    },
  })
  return client
}
