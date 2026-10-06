import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { api, call, type Schemas } from '../../api/client'
import { ErrorMessage } from '../../components/ErrorMessage'
import { Field } from '../../components/Field'
import { formatDate } from '../../i18n/format'
import { meKey } from '../auth/session'

const householdKey = ['household'] as const
const invitesKey = ['household', 'invites'] as const

export function HouseholdPage() {
  const { t } = useTranslation()
  const household = useQuery({
    queryKey: householdKey,
    queryFn: () => call(api.GET('/api/household')),
  })
  if (household.isError) return <ErrorMessage error={household.error} />
  if (!household.data) return <p>{t('app.loading')}</p>
  const h = household.data
  return (
    <section className="stack">
      <h1>{t('household.title')}</h1>
      <RenameForm name={h.name} />
      <h2>{t('household.members')}</h2>
      <ul className="list">
        {h.members.map((m) => (
          <li key={m.id}>
            <strong>{m.display_name}</strong>
            {m.is_me ? <span className="muted"> ({t('household.you')})</span> : null}
            <br />
            <small className="muted">
              {t('household.joined', { date: formatDate(m.joined_at) })}
            </small>
          </li>
        ))}
      </ul>
      <Invites household={h} />
    </section>
  )
}

function RenameForm({ name }: { name: string }) {
  const { t } = useTranslation()
  const client = useQueryClient()
  const [value, setValue] = useState(name)
  const rename = useMutation({
    mutationFn: () => call(api.PATCH('/api/household', { body: { name: value } })),
    onSuccess: (data) => {
      client.setQueryData(householdKey, data)
      void client.invalidateQueries({ queryKey: meKey })
    },
  })
  function submit(e: FormEvent) {
    e.preventDefault()
    rename.mutate()
  }
  return (
    <form onSubmit={submit} className="row">
      <Field
        label={t('household.name')}
        value={value}
        maxLength={80}
        required
        onChange={(e) => setValue(e.target.value)}
      />
      <button type="submit" disabled={rename.isPending || value === name}>
        {t('household.rename')}
      </button>
      <ErrorMessage error={rename.error} />
    </form>
  )
}

function Invites({ household }: { household: Schemas['HouseholdOut'] }) {
  const { t } = useTranslation()
  const client = useQueryClient()
  const [note, setNote] = useState('')
  const [issued, setIssued] = useState<Schemas['IssuedInviteOut'] | null>(null)
  const pending = useQuery({
    queryKey: invitesKey,
    queryFn: () => call(api.GET('/api/household/invites')),
  })
  const create = useMutation({
    mutationFn: () => call(api.POST('/api/household/invites', { body: { note: note || null } })),
    onSuccess: (data) => {
      setIssued(data)
      setNote('')
      void client.invalidateQueries({ queryKey: invitesKey })
    },
  })
  const revoke = useMutation({
    mutationFn: (id: string) =>
      call(
        api.DELETE('/api/household/invites/{invite_id}', { params: { path: { invite_id: id } } }),
      ),
    onSuccess: (_, id) => {
      if (issued?.invite.id === id) setIssued(null)
      void client.invalidateQueries({ queryKey: invitesKey })
    },
  })

  const seatsLeft = household.max_members - household.members.length - (pending.data?.length ?? 0)

  return (
    <>
      <h2>{t('household.invite.title')}</h2>
      {issued ? (
        <IssuedInvite issued={issued} />
      ) : seatsLeft > 0 ? (
        <form
          className="stack"
          onSubmit={(e) => {
            e.preventDefault()
            create.mutate()
          }}
        >
          <p className="muted">{t('household.invite.explain')}</p>
          <Field
            label={t('household.invite.note')}
            value={note}
            maxLength={120}
            onChange={(e) => setNote(e.target.value)}
          />
          <button type="submit" className="primary" disabled={create.isPending}>
            {t('household.invite.create')}
          </button>
        </form>
      ) : (
        <p className="muted">{t('household.invite.full', { max: household.max_members })}</p>
      )}
      <ErrorMessage error={create.error ?? revoke.error} />
      {pending.data && pending.data.length > 0 ? (
        <>
          <h3>{t('household.invite.pending')}</h3>
          <ul className="list">
            {pending.data.map((i) => (
              <li key={i.id} className="row spread">
                <span>
                  {i.note ?? '—'}
                  <br />
                  <small className="muted">
                    {t('household.invite.expires', { date: formatDate(i.expires_at) })}
                  </small>
                </span>
                <button type="button" onClick={() => revoke.mutate(i.id)}>
                  {t('household.invite.revoke')}
                </button>
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </>
  )
}

function IssuedInvite({ issued }: { issued: Schemas['IssuedInviteOut'] }) {
  const { t } = useTranslation()
  const [copied, setCopied] = useState(false)
  const text = t('household.invite.shareText', { link: issued.link, code: issued.code })
  return (
    <div className="card stack" data-testid="issued-invite">
      <div>
        <small className="muted">{t('household.invite.link')}</small>
        <p className="mono break" data-testid="invite-link">
          {issued.link}
        </p>
      </div>
      <div>
        <small className="muted">{t('household.invite.code')}</small>
        <p className="code" data-testid="invite-code">
          {issued.code}
        </p>
      </div>
      <small className="muted">
        {t('household.invite.expires', { date: formatDate(issued.invite.expires_at) })}
      </small>
      <div className="row">
        <button
          type="button"
          onClick={async () => {
            await navigator.clipboard?.writeText(issued.link)
            setCopied(true)
          }}
        >
          {copied ? t('common.copied') : t('common.copy')}
        </button>
        {'share' in navigator ? (
          <button type="button" onClick={() => void navigator.share({ text }).catch(() => {})}>
            {t('common.share')}
          </button>
        ) : null}
      </div>
    </div>
  )
}
