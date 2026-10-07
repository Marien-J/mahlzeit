import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { TFunction } from 'i18next'
import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { api, call, type Me } from '../../api/client'
import { ErrorMessage } from '../../components/ErrorMessage'
import { Field, SelectField } from '../../components/Field'
import { Sheet } from '../../components/Sheet'
import { uuid7 } from '../../lib/ids'
import { useMe } from '../auth/session'
import { CATEGORIES } from '../catalogue/LabelForm'
import {
  STORE_BRANDS,
  applyOps,
  arrange,
  suggest,
  type ListFields,
  type ListItem,
  type Store,
  type Suggestion,
} from './model'
import { enqueue, listKey, useHistory, useListQuery, useOutbox, useOutboxSender } from './sync'
import { useWakeLock } from './wakeLock'

const FILTER_KEY = 'mahlzeit.list.store'
const UNDO_MS = 6000

export function storeName(t: TFunction, store: Store | undefined): string {
  if (!store) return ''
  if (store.key) return STORE_BRANDS[store.key] ?? t('store.other')
  return store.name ?? ''
}

type Undo = { message: string; revert: () => void }

export function ListPage() {
  const me = useMe().data
  if (!me) return null
  return <ListScreen me={me} />
}

function ListScreen({ me }: { me: Me }) {
  const { t } = useTranslation()
  const client = useQueryClient()
  const household = me.household.id
  const query = useListQuery(household)
  const ops = useOutbox(household)
  useOutboxSender(client, household, ops.length)
  const [storeId, setStoreId] = useState<string | null>(() => {
    try {
      return localStorage.getItem(FILTER_KEY)
    } catch {
      return null
    }
  })
  const [shopping, setShopping] = useState(false)
  const [editing, setEditing] = useState<ListItem | null>(null)
  const [undo, setUndo] = useState<Undo | null>(null)
  useWakeLock(shopping)

  useEffect(() => {
    if (!undo) return
    const timer = window.setTimeout(() => setUndo(null), UNDO_MS)
    return () => window.clearTimeout(timer)
  }, [undo])

  const stores = query.data?.stores ?? []
  const items = useMemo(() => applyOps(query.data?.items ?? [], ops), [query.data, ops])
  const { aisles, done } = arrange(items, storeId)
  const byId = new Map(stores.map((s) => [s.id, s]))
  const usedStores = stores.filter((s) => items.some((i) => i.store_id === s.id))

  const send = (kind: 'add' | 'update' | 'remove', id: string, fields?: ListFields) =>
    enqueue(household, { kind, id, fields })

  const toggle = (item: ListItem) => {
    send('update', item.id, { checked: !item.checked })
    setUndo({
      message: t(item.checked ? 'list.unchecked' : 'list.checked', { text: item.text }),
      revert: () => send('update', item.id, { checked: item.checked }),
    })
  }

  const readd = (gone: ListItem[]) =>
    gone.forEach((i) =>
      send('add', uuid7(), {
        text: i.text,
        item_id: i.item_id,
        quantity: i.quantity,
        store_id: i.store_id,
        category: i.category,
        checked: i.checked,
        parse: false,
      }),
    )

  const remove = (gone: ListItem[]) => {
    gone.forEach((i) => send('remove', i.id))
    setUndo({ message: t('list.removed', { count: gone.length }), revert: () => readd(gone) })
  }

  const chooseStore = (id: string | null) => {
    setStoreId(id)
    try {
      if (id) localStorage.setItem(FILTER_KEY, id)
      else localStorage.removeItem(FILTER_KEY)
    } catch {
      // the filter is only remembered while the page is open
    }
  }

  const loading = !query.data && query.isPending
  return (
    <section className={shopping ? 'list-page shopping' : 'list-page'}>
      <header className="row spread">
        <h1>{t('list.title')}</h1>
        <button
          type="button"
          className={shopping ? 'primary' : undefined}
          aria-pressed={shopping}
          onClick={() => setShopping((s) => !s)}
        >
          {shopping ? t('list.doneShopping') : t('list.shop')}
        </button>
      </header>

      {!shopping ? <AddField household={household} me={me} onAdd={send} /> : null}

      {usedStores.length ? (
        <div className="chips" role="group" aria-label={t('list.storeFilter')}>
          <button
            type="button"
            aria-pressed={storeId === null}
            className={storeId === null ? 'chip active' : 'chip'}
            onClick={() => chooseStore(null)}
          >
            {t('list.allStores')}
          </button>
          {usedStores.map((s) => (
            <button
              key={s.id}
              type="button"
              aria-pressed={storeId === s.id}
              className={storeId === s.id ? 'chip active' : 'chip'}
              onClick={() => chooseStore(s.id)}
            >
              {storeName(t, s)}
            </button>
          ))}
        </div>
      ) : null}

      {ops.length > 0 && !navigator.onLine ? (
        <p className="muted" role="status" data-testid="pending">
          {t('list.pending', { count: ops.length })}
        </p>
      ) : null}
      {loading ? <p className="muted">{t('app.loading')}</p> : null}
      {query.data && aisles.length === 0 && done.length === 0 ? (
        <p className="muted">{t('list.empty')}</p>
      ) : null}

      {aisles.map((aisle) => (
        <section
          key={aisle.category}
          className="aisle"
          aria-label={t(`category.${aisle.category}`)}
        >
          <h2>{t(`category.${aisle.category}`)}</h2>
          <ul className="list-rows">
            {aisle.items.map((item) => (
              <Row
                key={item.id}
                item={item}
                store={item.store_id ? byId.get(item.store_id) : undefined}
                onToggle={() => toggle(item)}
                onOpen={() => setEditing(item)}
              />
            ))}
          </ul>
        </section>
      ))}

      {done.length ? (
        <section className="aisle done" aria-label={t('list.done')}>
          <div className="row spread">
            <h2>{t('list.doneCount', { count: done.length })}</h2>
            <button type="button" onClick={() => remove(done)}>
              {t('list.clearChecked')}
            </button>
          </div>
          <ul className="list-rows">
            {done.map((item) => (
              <Row
                key={item.id}
                item={item}
                store={item.store_id ? byId.get(item.store_id) : undefined}
                onToggle={() => toggle(item)}
                onOpen={() => setEditing(item)}
              />
            ))}
          </ul>
        </section>
      ) : null}

      {undo ? (
        <div className="snackbar" role="status">
          <span>{undo.message}</span>
          <button
            type="button"
            onClick={() => {
              undo.revert()
              setUndo(null)
            }}
          >
            {t('list.undo')}
          </button>
        </div>
      ) : null}

      {editing ? (
        <ItemSheet
          item={editing}
          stores={stores}
          onClose={() => setEditing(null)}
          onSave={(fields) => {
            if (Object.keys(fields).length) send('update', editing.id, fields)
            setEditing(null)
          }}
          onRemove={() => {
            remove([editing])
            setEditing(null)
          }}
          onStoreCreated={() => void client.invalidateQueries({ queryKey: listKey })}
        />
      ) : null}
    </section>
  )
}

function Row({
  item,
  store,
  onToggle,
  onOpen,
}: {
  item: ListItem
  store: Store | undefined
  onToggle: () => void
  onOpen: () => void
}) {
  const { t } = useTranslation()
  return (
    <li className={item.checked ? 'list-row checked' : 'list-row'}>
      <button
        type="button"
        role="checkbox"
        aria-checked={item.checked}
        aria-label={item.text}
        className="check"
        onClick={onToggle}
      />
      <button type="button" className="what" onClick={onOpen}>
        <span>{item.text}</span>
        {item.quantity ? <span className="qty">{item.quantity}</span> : null}
        {store ? <span className="store-badge">{storeName(t, store)}</span> : null}
      </button>
    </li>
  )
}

function useCatalogueHits(query: string) {
  const q = query.trim()
  return useQuery({
    queryKey: ['items', 'list', q],
    queryFn: () => call(api.GET('/api/items', { params: { query: { q, limit: 6 } } })),
    enabled: q.length >= 2,
    staleTime: 60_000,
    placeholderData: (previous) => previous,
  })
}

function AddField({
  household,
  me,
  onAdd,
}: {
  household: string
  me: Me
  onAdd: (kind: 'add', id: string, fields: ListFields) => void
}) {
  const { t } = useTranslation()
  const [text, setText] = useState('')
  const input = useRef<HTMLInputElement>(null)
  const history = useHistory(household)
  const catalogue = useCatalogueHits(text)
  const suggestions = suggest(
    text,
    history.data ?? [],
    navigator.onLine && text.trim().length >= 2
      ? (catalogue.data ?? []).map((i) => ({ id: i.id, name: i.name, category: i.category }))
      : [],
  )
  const done = () => {
    setText('')
    input.current?.focus()
  }
  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (!text.trim()) return
    onAdd('add', uuid7(), { text: text.trim(), parse: true })
    done()
  }
  const pick = (s: Suggestion) => {
    const fields: ListFields = { text: s.text, parse: false }
    if (s.item_id) fields.item_id = s.item_id
    if (s.category) fields.category = s.category
    if (s.store_id) fields.store_id = s.store_id
    onAdd('add', uuid7(), fields)
    done()
  }
  return (
    <form className="add-field" onSubmit={submit} role="search" lang={me.user.language}>
      <div className="row">
        <Field
          ref={input}
          label={t('list.add')}
          value={text}
          autoComplete="off"
          enterKeyHint="done"
          onChange={(e) => setText(e.target.value)}
        />
        <button type="submit" className="primary" disabled={!text.trim()}>
          {t('list.addButton')}
        </button>
      </div>
      {suggestions.length ? (
        <ul className="suggestions" aria-label={t('list.suggestions')}>
          {suggestions.map((s) => (
            <li key={s.key}>
              <button type="button" onClick={() => pick(s)}>
                <span>{s.text}</span>
                {s.category ? <small className="muted">{t(`category.${s.category}`)}</small> : null}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </form>
  )
}

function ItemSheet({
  item,
  stores,
  onClose,
  onSave,
  onRemove,
  onStoreCreated,
}: {
  item: ListItem
  stores: Store[]
  onClose: () => void
  onSave: (fields: ListFields) => void
  onRemove: () => void
  onStoreCreated: () => void
}) {
  const { t } = useTranslation()
  const [text, setText] = useState(item.text)
  const [quantity, setQuantity] = useState(item.quantity ?? '')
  const [storeId, setStoreId] = useState(item.store_id ?? '')
  const [category, setCategory] = useState(item.category)
  const [newStore, setNewStore] = useState<string | null>(null)
  const create = useMutation({
    mutationFn: (name: string) => call(api.POST('/api/stores', { body: { name } })),
    onSuccess: (store) => {
      setStoreId(store.id)
      setNewStore(null)
      onStoreCreated()
    },
  })
  const save = (e: FormEvent) => {
    e.preventDefault()
    const fields: ListFields = {}
    if (text.trim() && text.trim() !== item.text) fields.text = text.trim()
    if ((quantity.trim() || null) !== item.quantity) fields.quantity = quantity.trim() || null
    if ((storeId || null) !== item.store_id) fields.store_id = storeId || null
    if (category !== item.category) fields.category = category
    onSave(fields)
  }
  return (
    <Sheet title={item.text} onClose={onClose}>
      <form className="stack" onSubmit={save}>
        <Field
          label={t('list.text')}
          value={text}
          required
          onChange={(e) => setText(e.target.value)}
        />
        <Field
          label={t('list.quantity')}
          value={quantity}
          maxLength={40}
          onChange={(e) => setQuantity(e.target.value)}
        />
        <SelectField
          label={t('list.store')}
          value={storeId}
          options={[
            { value: '', label: t('list.anyStore') },
            ...stores.map((s) => ({ value: s.id, label: storeName(t, s) })),
          ]}
          onChange={setStoreId}
        />
        {newStore === null ? (
          <button type="button" className="link" onClick={() => setNewStore('')}>
            {t('list.newStore')}
          </button>
        ) : (
          <div className="row">
            <Field
              label={t('list.newStoreName')}
              value={newStore}
              maxLength={40}
              onChange={(e) => setNewStore(e.target.value)}
            />
            <button
              type="button"
              disabled={!newStore.trim() || create.isPending}
              onClick={() => create.mutate(newStore.trim())}
            >
              {t('list.createStore')}
            </button>
          </div>
        )}
        <ErrorMessage error={create.error} />
        <SelectField
          label={t('list.aisle')}
          value={category}
          options={CATEGORIES.map((c) => ({ value: c, label: t(`category.${c}`) }))}
          onChange={setCategory}
        />
        <div className="row spread">
          <button type="button" className="danger" onClick={onRemove}>
            {t('list.remove')}
          </button>
          <button type="submit" className="primary">
            {t('common.save')}
          </button>
        </div>
      </form>
    </Sheet>
  )
}
