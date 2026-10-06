import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, api, call, setCsrfToken } from './client'
import { mockApi, reply } from '../test/server'

afterEach(() => {
  setCsrfToken(null)
  vi.unstubAllGlobals()
})

describe('api client', () => {
  it('sends the CSRF token on unsafe requests only', async () => {
    const server = mockApi({
      'GET /api/household': () => ({ id: 'h', name: 'x', members: [], max_members: 4 }),
      'POST /api/auth/logout': () => reply(204),
    })
    setCsrfToken('tok')
    await call(api.GET('/api/household'))
    await call(api.POST('/api/auth/logout'))
    expect(server.calls[0]?.headers.get('X-CSRF-Token')).toBeNull()
    expect(server.calls[1]?.headers.get('X-CSRF-Token')).toBe('tok')
  })

  it('turns error bodies into ApiError with code and detail', async () => {
    mockApi({
      'POST /api/auth/login': () =>
        reply(429, { code: 'too_many_attempts', detail: { minutes: 15 } }),
    })
    const err = await call(
      api.POST('/api/auth/login', { body: { email: 'a', password: 'b' } }),
    ).catch((e: unknown) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err).toMatchObject({ status: 429, code: 'too_many_attempts', detail: { minutes: 15 } })
  })

  it('reports network failures as code "network"', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    await expect(call(api.GET('/api/health'))).rejects.toMatchObject({ status: 0, code: 'network' })
  })
})
