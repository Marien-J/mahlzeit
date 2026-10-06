import { vi } from 'vitest'

const REPLY = Symbol('reply')
type Reply = { [REPLY]: true; status: number; body?: unknown }

/** An explicit status code; any other return value is sent as a 200 JSON body. */
export function reply(status: number, body?: unknown): Reply {
  return { [REPLY]: true, status, body }
}

type Handler = (body: unknown, request: Request) => unknown

/** A tiny fake API: routes keyed "METHOD /path". Unknown routes answer 404. */
export function mockApi(routes: Record<string, Handler>) {
  const calls: { method: string; path: string; body: unknown; headers: Headers }[] = []
  const fetchMock = vi.fn(async (input: Request) => {
    const url = new URL(input.url)
    const key = `${input.method} ${url.pathname}`
    const text = input.method === 'GET' ? '' : await input.text()
    const body = text ? (JSON.parse(text) as unknown) : undefined
    calls.push({ method: input.method, path: url.pathname, body, headers: input.headers })
    const handler = routes[key]
    if (!handler) return json(404, { code: 'not_found', detail: {} })
    const result = handler(body, input)
    if (result && typeof result === 'object' && REPLY in result) {
      const r = result as Reply
      return json(r.status, r.body)
    }
    return json(200, result)
  })
  vi.stubGlobal('fetch', fetchMock)
  return { calls, fetchMock }
}

function json(status: number, body: unknown): Response {
  if (status === 204) return new Response(null, { status })
  return new Response(JSON.stringify(body ?? null), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

export const ME = {
  user: {
    id: '0192f1c4-0000-7000-8000-000000000001',
    email: 'jonas@example.org',
    display_name: 'Jonas',
    language: 'de',
    time_zone: 'Europe/Berlin',
    is_admin: true,
  },
  profile: {
    show_workouts: true,
    show_body: false,
    share_ai_usage: false,
    start_screen: 'today',
    push_offers: true,
  },
  household: { id: '0192f1c4-0000-7000-8000-0000000000aa', name: 'Zuhause' },
  csrf_token: 'csrf-123',
}
