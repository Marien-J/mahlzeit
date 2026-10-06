import createClient, { type Middleware } from 'openapi-fetch'
import type { components, paths } from './schema'

export type Schemas = components['schemas']
export type Me = Schemas['MeOut']

const UNSAFE = new Set(['POST', 'PUT', 'PATCH', 'DELETE'])
let csrfToken: string | null = null

/** The CSRF token comes with /api/auth/me and is sent back on every unsafe request. */
export function setCsrfToken(token: string | null): void {
  csrfToken = token
}

const csrf: Middleware = {
  onRequest({ request }) {
    if (csrfToken && UNSAFE.has(request.method)) request.headers.set('X-CSRF-Token', csrfToken)
    return request
  },
}

/** An API failure with the server's error code; the UI translates `errors.<code>`. */
export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly detail: Record<string, unknown>

  constructor(status: number, code: string, detail: Record<string, unknown> = {}) {
    super(code)
    this.status = status
    this.code = code
    this.detail = detail
  }
}

export function createApi(baseUrl: string, fetchImpl?: typeof fetch) {
  const client = createClient<paths>({
    baseUrl,
    credentials: 'same-origin',
    // Resolve fetch on every call, so tests and the service worker can replace it.
    fetch: fetchImpl ?? ((request: Request) => globalThis.fetch(request)),
  })
  client.use(csrf)
  return client
}

export const api = createApi(typeof window === 'undefined' ? '' : window.location.origin)

type Result<T> = { data?: T; error?: unknown; response: Response }

/** Await an openapi-fetch call and return its data or throw an ApiError. */
export async function call<T>(request: Promise<Result<T>>): Promise<T> {
  let result: Result<T>
  try {
    result = await request
  } catch {
    throw new ApiError(0, 'network')
  }
  if (result.response.ok) return result.data as T
  const body = result.error as { code?: unknown; detail?: unknown } | undefined
  const code = typeof body?.code === 'string' ? body.code : 'unknown'
  const detail =
    body?.detail && typeof body.detail === 'object' ? (body.detail as Record<string, unknown>) : {}
  throw new ApiError(result.response.status, code, detail)
}
