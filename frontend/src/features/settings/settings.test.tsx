import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import i18n from '../../i18n'
import { ME, mockApi, reply } from '../../test/server'
import { renderApp } from '../../test/render'

beforeEach(async () => {
  await i18n.changeLanguage('de')
})
afterEach(() => vi.unstubAllGlobals())

describe('settings', () => {
  it('switches the language for this user and the whole UI', async () => {
    let me = ME
    const server = mockApi({
      'GET /api/auth/me': () => me,
      'GET /api/push': () => ({ configured: true, public_key: 'BPk', devices: 0 }),
      'PATCH /api/me': (body) => {
        me = { ...me, user: { ...me.user, ...(body as object) } }
        return me
      },
    })
    renderApp('/settings')
    const user = userEvent.setup()
    expect(await screen.findByRole('heading', { name: 'Einstellungen' })).toBeInTheDocument()
    await user.selectOptions(screen.getByLabelText('Sprache'), 'nl')
    expect(await screen.findByRole('heading', { name: 'Instellingen' })).toBeInTheDocument()
    expect(
      within(screen.getByRole('navigation', { name: 'Hoofdmenu' })).getByText('Vandaag'),
    ).toBeInTheDocument()
    expect(server.calls.find((c) => c.method === 'PATCH')?.headers.get('X-CSRF-Token')).toBe(
      'csrf-123',
    )
    expect(document.documentElement.lang).toBe('nl')
  })

  it('saves sharing switches', async () => {
    let me = ME
    const server = mockApi({
      'GET /api/auth/me': () => me,
      'GET /api/push': () => ({ configured: false, public_key: null, devices: 0 }),
      'PATCH /api/me/profile': (body) => {
        me = { ...me, profile: { ...me.profile, ...(body as object) } }
        return me
      },
    })
    renderApp('/settings')
    const user = userEvent.setup()
    const body = await screen.findByRole('switch', {
      name: 'Mein Gewicht und meinen Bauchumfang zeigen',
    })
    expect(body).not.toBeChecked()
    await user.click(body)
    expect(
      await screen.findByRole('switch', { name: 'Mein Gewicht und meinen Bauchumfang zeigen' }),
    ).toBeChecked()
    expect(server.calls.find((c) => c.method === 'PATCH')?.body).toEqual({ show_body: true })
  })
})

describe('household', () => {
  it('creates a partner invitation and shows link and code', async () => {
    let invites: object[] = []
    mockApi({
      'GET /api/auth/me': () => ME,
      'GET /api/household': () => ({
        id: ME.household.id,
        name: 'Zuhause',
        max_members: 4,
        members: [
          { id: ME.user.id, display_name: 'Jonas', joined_at: '2026-10-01T10:00:00Z', is_me: true },
        ],
      }),
      'GET /api/household/invites': () => invites,
      'POST /api/household/invites': () => {
        const invite = {
          id: 'i1',
          created_at: '2026-10-06T12:00:00Z',
          expires_at: '2026-10-13T12:00:00Z',
          note: null,
        }
        invites = [invite]
        return reply(201, { invite, link: 'http://localhost/join/tok', code: 'ABCD-EFGH' })
      },
    })
    renderApp('/household')
    const user = userEvent.setup()
    expect(await screen.findByText('Jonas')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Einladung erstellen' }))
    expect(await screen.findByTestId('invite-code')).toHaveTextContent('ABCD-EFGH')
    expect(screen.getByTestId('invite-link')).toHaveTextContent('http://localhost/join/tok')
    expect(await screen.findByRole('button', { name: 'Zurückziehen' })).toBeInTheDocument()
  })
})

describe('Claude connector', () => {
  it('shows a new personal link once and can turn it off', async () => {
    let active = false
    const server = mockApi({
      'GET /api/auth/me': () => ME,
      'GET /api/push': () => ({ configured: true, public_key: 'BPk', devices: 0 }),
      'GET /api/connector': () => ({
        active,
        created_at: active ? '2026-10-06T10:00:00Z' : null,
        last_used_at: null,
      }),
      'POST /api/connector': () => {
        active = true
        return reply(201, { url: 'http://localhost/mcp/secret-token' })
      },
      'DELETE /api/connector': () => {
        active = false
        return reply(204)
      },
    })
    renderApp('/settings')
    const user = userEvent.setup()
    expect(await screen.findByText('Noch kein Link.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Link erstellen' }))
    expect(await screen.findByLabelText('Connector-Link')).toHaveValue(
      'http://localhost/mcp/secret-token',
    )
    expect(await screen.findByText(/Noch nicht benutzt/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Ausschalten' }))
    expect(await screen.findByText('Noch kein Link.')).toBeInTheDocument()
    expect(screen.queryByLabelText('Connector-Link')).toBeNull()
    expect(server.calls.filter((c) => c.path === '/api/connector').map((c) => c.method)).toEqual(
      expect.arrayContaining(['POST', 'DELETE']),
    )
  })
})
