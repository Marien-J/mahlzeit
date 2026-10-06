import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { api, call } from '../../api/client'
import { ErrorMessage } from '../../components/ErrorMessage'
import { Field, Toggle } from '../../components/Field'
import { Sheet } from '../../components/Sheet'
import { Star } from '../../components/Star'
import { kcal } from '../../lib/nutrition'
import { useMe } from '../auth/session'
import { itemToItemIn, setFavourite, useSavedMeals, type Item, type SavedMeal } from './api'
import { EMPTY_ITEM, LabelForm } from './LabelForm'

function useOwnItems(query: string) {
  return useQuery({
    queryKey: ['items', 'own', query],
    queryFn: () =>
      call(api.GET('/api/items', { params: { query: { q: query, own: true, limit: 200 } } })),
    placeholderData: (previous) => previous,
  })
}

/** The household's own foods and saved meals. Generic foods are read-only. */
export function FoodsPage() {
  const { t } = useTranslation()
  const me = useMe().data
  const client = useQueryClient()
  const [query, setQuery] = useState('')
  const own = useOwnItems(query)
  const [editing, setEditing] = useState<Item | 'new' | null>(null)
  if (!me) return null

  const saved = () => {
    void client.invalidateQueries({ queryKey: ['items'] })
    setEditing(null)
  }

  return (
    <section className="stack">
      <header className="row spread">
        <h1>{t('foods.title')}</h1>
        <button type="button" className="primary" onClick={() => setEditing('new')}>
          {t('foods.new')}
        </button>
      </header>
      <Field
        label={t('foods.search')}
        type="search"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
      />
      {own.data && own.data.length === 0 ? <p className="muted">{t('foods.none')}</p> : null}
      <ul className="list results" data-testid="own-items">
        {(own.data ?? []).map((item) => (
          <li key={item.id}>
            <button type="button" className="result" onClick={() => setEditing(item)}>
              <span>
                {item.favourite ? <Star /> : null}
                {item.name}
                {item.brand ? <small className="muted"> · {item.brand}</small> : null}
              </span>
              <small className="muted">
                {t('amount.per100', { unit: item.base_unit, kcal: kcal(item.nutrients.kcal) })}
              </small>
            </button>
          </li>
        ))}
      </ul>

      <h2>{t('meals.title')}</h2>
      <SavedMealList />
      <Link to="/settings">{t('common.back')}</Link>

      {editing ? (
        <Sheet
          title={editing === 'new' ? t('foods.new') : editing.name}
          onClose={() => setEditing(null)}
        >
          {editing === 'new' ? null : <FavouriteToggle item={editing} />}
          <LabelForm
            initial={editing === 'new' ? EMPTY_ITEM : itemToItemIn(editing)}
            itemId={editing === 'new' ? undefined : editing.id}
            language={me.user.language}
            onSaved={saved}
          />
        </Sheet>
      ) : null}
    </section>
  )
}

export function FavouriteToggle({ item }: { item: Item }) {
  const { t } = useTranslation()
  const client = useQueryClient()
  const [on, setOn] = useState(item.favourite)
  const toggle = useMutation({
    mutationFn: (value: boolean) => setFavourite(item.id, value),
    onSuccess: (_, value) => {
      setOn(value)
      void client.invalidateQueries({ queryKey: ['items'] })
    },
  })
  return (
    <>
      <Toggle
        label={t('foods.favourite')}
        checked={on}
        disabled={toggle.isPending}
        onChange={(v) => toggle.mutate(v)}
      />
      <ErrorMessage error={toggle.error} />
    </>
  )
}

function SavedMealList() {
  const { t } = useTranslation()
  const meals = useSavedMeals()
  const [open, setOpen] = useState<SavedMeal | null>(null)
  if (meals.data && meals.data.length === 0) return <p className="muted">{t('meals.none')}</p>
  return (
    <>
      <ul className="list results" data-testid="saved-meals">
        {(meals.data ?? []).map((m) => (
          <li key={m.id}>
            <button type="button" className="result" onClick={() => setOpen(m)}>
              <span>{m.name}</span>
              <small className="muted">
                {t('totals.kcal', { value: kcal(m.per_serving.values.kcal) })}
              </small>
            </button>
          </li>
        ))}
      </ul>
      {open ? <SavedMealSheet meal={open} onClose={() => setOpen(null)} /> : null}
    </>
  )
}

function SavedMealSheet({ meal, onClose }: { meal: SavedMeal; onClose: () => void }) {
  const { t } = useTranslation()
  const client = useQueryClient()
  const [name, setName] = useState(meal.name)
  const done = () => {
    void client.invalidateQueries({ queryKey: ['saved-meals'] })
    onClose()
  }
  const rename = useMutation({
    mutationFn: () =>
      call(
        api.PATCH('/api/saved-meals/{meal_id}', {
          params: { path: { meal_id: meal.id } },
          body: { name },
        }),
      ),
    onSuccess: done,
  })
  const remove = useMutation({
    mutationFn: () =>
      call(api.DELETE('/api/saved-meals/{meal_id}', { params: { path: { meal_id: meal.id } } })),
    onSuccess: done,
  })
  const submit = (e: FormEvent) => {
    e.preventDefault()
    rename.mutate()
  }
  return (
    <Sheet title={meal.name} onClose={onClose}>
      <ul className="list compact">
        {meal.ingredients.map((i) => (
          <li key={i.item_id} className="row spread">
            <span>{i.name}</span>
            <span className="muted">
              {i.amount} {i.base_unit}
            </span>
          </li>
        ))}
      </ul>
      <form className="row" onSubmit={submit}>
        <Field
          label={t('meals.name')}
          value={name}
          required
          maxLength={120}
          onChange={(e) => setName(e.target.value)}
        />
        <button type="submit" disabled={rename.isPending || name === meal.name}>
          {t('common.save')}
        </button>
      </form>
      <ErrorMessage error={rename.error ?? remove.error} />
      <button
        type="button"
        className="danger"
        disabled={remove.isPending}
        onClick={() => remove.mutate()}
      >
        {t('meals.delete')}
      </button>
    </Sheet>
  )
}
