import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import i18n from '../../i18n'
import { ME, mockApi, reply } from '../../test/server'
import { renderApp } from '../../test/render'
import { safeNext } from './LoginPage'

const unauthenticated = reply(401, { code: 'not_authenticated', detail: {} })

beforeEach(async () => {
  await i18n.changeLanguage('de')
})
afterEach(() => vi.unstubAllGlobals())

describe('sign-in', () => {
  it('sends signed-out visitors to the login page', async () => {
    mockApi({ 'GET /api/auth/me': () => unauthenticated })
    const { router } = renderApp('/settings')
    expect(await screen.findByRole('heading', { name: 'Anmelden' })).toBeInTheDocument()
    expect(router.state.location.search).toBe('?next=%2Fsettings')
  })

  it('logs in, adopts the user language and returns to the requested page', async () => {
    let signedIn = false
    const server = mockApi({
      'GET /api/auth/me': () =>
        signedIn ? { ...ME, user: { ...ME.user, language: 'en' } } : unauthenticated,
      'POST /api/auth/login': () => {
        signedIn = true
        return { ...ME, user: { ...ME.user, language: 'en' } }
      },
      'GET /api/push': () => ({ configured: false, public_key: null, devices: 0 }),
    })
    const { router } = renderApp('/login?next=%2Fsettings')
    const user = userEvent.setup()
    await user.type(await screen.findByLabelText('E-Mail'), 'jonas@example.org')
    await user.type(screen.getByLabelText('Passwort'), 'correct horse battery')
    await user.click(screen.getByRole('button', { name: 'Anmelden' }))
    expect(await screen.findByRole('heading', { name: 'Settings' })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/settings')
    expect(server.calls.find((c) => c.path === '/api/auth/login')?.body).toEqual({
      email: 'jonas@example.org',
      password: 'correct horse battery',
    })
  })

  it('shows a translated error for a wrong password', async () => {
    mockApi({
      'GET /api/auth/me': () => unauthenticated,
      'POST /api/auth/login': () => reply(401, { code: 'invalid_credentials', detail: {} }),
    })
    renderApp('/login')
    const user = userEvent.setup()
    await user.type(await screen.findByLabelText('E-Mail'), 'a@example.org')
    await user.type(screen.getByLabelText('Passwort'), 'nope')
    await user.click(screen.getByRole('button', { name: 'Anmelden' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('E-Mail oder Passwort ist falsch.')
  })

  it('switches language before sign-in', async () => {
    mockApi({ 'GET /api/auth/me': () => unauthenticated })
    renderApp('/login')
    const user = userEvent.setup()
    await user.selectOptions(await screen.findByLabelText('Sprache'), 'nl')
    expect(await screen.findByRole('heading', { name: 'Inloggen' })).toBeInTheDocument()
  })

  it('only follows same-app paths after sign-in', () => {
    expect(safeNext('/household')).toBe('/household')
    expect(safeNext('//evil.example')).toBe('/')
    expect(safeNext('https://evil.example')).toBe('/')
    expect(safeNext(null)).toBe('/')
  })
})

describe('joining by invite', () => {
  it('previews a partner invite and creates the account', async () => {
    let joined = false
    const server = mockApi({
      'GET /api/auth/me': () =>
        joined ? { ...ME, user: { ...ME.user, display_name: 'Sam' } } : unauthenticated,
      'GET /api/invites/ABCD-EFGH': () => ({
        kind: 'partner',
        status: 'pending',
        household_name: 'Zuhause',
        inviter_name: 'Jonas',
        language: 'de',
        expires_at: '2026-10-13T12:00:00Z',
      }),
      'POST /api/invites/accept': () => {
        joined = true
        return reply(201, { ...ME, user: { ...ME.user, display_name: 'Sam' } })
      },
    })
    const { router } = renderApp('/join')
    const user = userEvent.setup()
    await user.type(await screen.findByLabelText('Einladungscode'), 'ABCD-EFGH')
    await user.click(screen.getByRole('button', { name: 'Weiter' }))
    expect(
      await screen.findByText('Jonas lädt dich in den Haushalt „Zuhause“ ein.'),
    ).toBeInTheDocument()
    await user.type(screen.getByLabelText('Dein Name'), 'Sam')
    await user.type(screen.getByLabelText('E-Mail'), 'sam@example.org')
    await user.type(screen.getByLabelText('Passwort'), 'a long password')
    await user.click(screen.getByRole('button', { name: 'Konto anlegen' }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/'))
    expect(await screen.findByRole('heading', { name: 'Hallo, Sam' })).toBeInTheDocument()
    const body = server.calls.find((c) => c.path === '/api/invites/accept')?.body as Record<
      string,
      unknown
    >
    expect(body).toMatchObject({
      key: 'ABCD-EFGH',
      display_name: 'Sam',
      language: 'de',
      household_name: null,
    })
    expect(typeof body.time_zone).toBe('string')
  })

  it('explains an expired invite', async () => {
    mockApi({
      'GET /api/auth/me': () => unauthenticated,
      'GET /api/invites/tok': () => ({
        kind: 'partner',
        status: 'expired',
        household_name: 'Zuhause',
        inviter_name: 'Jonas',
        language: 'de',
        expires_at: '2026-10-01T12:00:00Z',
      }),
    })
    renderApp('/join/tok')
    expect(
      await screen.findByText('Diese Einladung ist abgelaufen. Bitte um eine neue.'),
    ).toBeInTheDocument()
  })

  it('offers to type a code when the link is unknown', async () => {
    mockApi({
      'GET /api/auth/me': () => unauthenticated,
      'GET /api/invites/bad': () => reply(404, { code: 'invite_not_found', detail: {} }),
    })
    renderApp('/join/bad')
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Keine Einladung mit diesem Code oder Link.',
    )
    expect(screen.getByLabelText('Einladungscode')).toBeInTheDocument()
  })
})

describe('password reset', () => {
  it('points to the admin command when the server cannot send email', async () => {
    mockApi({
      'GET /api/auth/me': () => unauthenticated,
      'GET /api/config': () => ({
        version: '0.1.0',
        languages: ['de', 'en', 'nl'],
        email_reset: false,
        push_public_key: null,
      }),
    })
    renderApp('/forgot')
    expect(await screen.findByText(/mahlzeit reset-password/)).toBeInTheDocument()
  })
})

describe('join form', () => {
  it('has exactly one language switch', async () => {
    mockApi({
      'GET /api/auth/me': () => unauthenticated,
      'GET /api/invites/tok': () => ({
        kind: 'household',
        status: 'pending',
        household_name: null,
        inviter_name: null,
        language: 'de',
        expires_at: '2026-10-13T12:00:00Z',
      }),
    })
    renderApp('/join/tok')
    expect(await screen.findByLabelText('Name des Haushalts')).toBeInTheDocument()
    expect(screen.getAllByLabelText('Sprache')).toHaveLength(1)
  })
})

describe('offline start', () => {
  it('shows the last signed-in user while the server cannot be reached', async () => {
    localStorage.setItem('mahlzeit.me', JSON.stringify({ ...ME, csrf_token: undefined }))
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    renderApp('/')
    expect(await screen.findByRole('heading', { name: 'Hallo, Jonas' })).toBeInTheDocument()
    localStorage.clear()
  })

  it('forgets the cached user when the session is gone', async () => {
    localStorage.setItem('mahlzeit.me', JSON.stringify(ME))
    mockApi({ 'GET /api/auth/me': () => unauthenticated })
    renderApp('/')
    expect(await screen.findByRole('heading', { name: 'Anmelden' })).toBeInTheDocument()
    expect(localStorage.getItem('mahlzeit.me')).toBeNull()
  })
})
