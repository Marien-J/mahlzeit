import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { ErrorMessage } from '../../components/ErrorMessage'
import { Sheet } from '../../components/Sheet'
import { formatNumber } from '../../i18n/format'
import { grams, kcal } from '../../lib/nutrition'
import { useRecipes, type Recipe } from '../catalogue/api'
import { addToList, deleteRecipe } from './api'
import { RecipeEditor } from './RecipeEditor'

export function RecipesPage() {
  const { t } = useTranslation()
  const recipes = useRecipes('recipe')
  const [open, setOpen] = useState<Recipe | null>(null)
  const [editing, setEditing] = useState<Recipe | 'new' | null>(null)
  const staples = (recipes.data ?? []).filter((r) => r.staple)
  const others = (recipes.data ?? []).filter((r) => !r.staple)

  return (
    <section className="stack">
      <header className="row spread">
        <h1>{t('recipes.title')}</h1>
        <button type="button" className="primary" onClick={() => setEditing('new')}>
          {t('recipes.new')}
        </button>
      </header>
      <ErrorMessage error={recipes.error} />
      {recipes.data && recipes.data.length === 0 ? (
        <p className="muted">{t('recipes.none')}</p>
      ) : null}
      <RecipeList title={t('recipes.staples')} recipes={staples} onOpen={setOpen} />
      <RecipeList title={t('recipes.others')} recipes={others} onOpen={setOpen} />
      <p>
        <Link to="/foods">{t('recipes.savedMeals')}</Link>
      </p>
      {open ? (
        <RecipeSheet
          recipe={open}
          onEdit={() => {
            setEditing(open)
            setOpen(null)
          }}
          onClose={() => setOpen(null)}
        />
      ) : null}
      {editing ? (
        <RecipeEditor
          recipe={editing === 'new' ? null : editing}
          onDone={() => setEditing(null)}
          onClose={() => setEditing(null)}
        />
      ) : null}
    </section>
  )
}

function RecipeList({
  title,
  recipes,
  onOpen,
}: {
  title: string
  recipes: Recipe[]
  onOpen: (recipe: Recipe) => void
}) {
  const { t } = useTranslation()
  if (recipes.length === 0) return null
  return (
    <div className="stack">
      <h2>{title}</h2>
      <ul className="list results" data-testid="recipes">
        {recipes.map((r) => (
          <li key={r.id}>
            <button type="button" className="result" onClick={() => onOpen(r)}>
              <span>{r.name}</span>
              <small className="muted">
                {t('recipes.servingsCount', { count: r.servings, n: formatNumber(r.servings) })} ·{' '}
                {t('recipes.perServing', { kcal: kcal(r.per_serving.values.kcal) })}
              </small>
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}

function RecipeSheet({
  recipe,
  onEdit,
  onClose,
}: {
  recipe: Recipe
  onEdit: () => void
  onClose: () => void
}) {
  const { t } = useTranslation()
  const client = useQueryClient()
  const [portions, setPortions] = useState(String(recipe.servings))
  const [confirming, setConfirming] = useState(false)
  const toList = useMutation({
    mutationFn: () => addToList(recipe.id, Number(portions.replace(',', '.'))),
    onSuccess: () => void client.invalidateQueries({ queryKey: ['list'] }),
  })
  const remove = useMutation({
    mutationFn: () => deleteRecipe(recipe.id),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ['recipes'] })
      onClose()
    },
  })
  const per = recipe.per_serving.values
  return (
    <Sheet title={recipe.name} onClose={onClose}>
      <div className="stack">
        <p className="muted">
          {t('recipes.servingsCount', { count: recipe.servings, n: formatNumber(recipe.servings) })}
          {recipe.cooked_yield_g != null
            ? ` · ${t('recipes.cookedYieldValue', { grams: formatNumber(recipe.cooked_yield_g) })}`
            : ''}
        </p>
        <p>{t('recipes.nutrition', { kcal: kcal(per.kcal), protein: grams(per.protein) })}</p>
        <ul className="list compact">
          {recipe.ingredients.map((i) => (
            <li key={i.item_id} className="row spread">
              <span>{i.name}</span>
              <span className="muted">
                {formatNumber(i.amount)} {i.base_unit}
              </span>
            </li>
          ))}
        </ul>
        {recipe.notes ? <p className="notes">{recipe.notes}</p> : null}
        <div className="row">
          <label className="field">
            <span>{t('recipes.listPortions')}</span>
            <input
              inputMode="decimal"
              value={portions}
              onChange={(e) => setPortions(e.target.value)}
            />
          </label>
          <button
            type="button"
            className="primary"
            disabled={toList.isPending || !(Number(portions.replace(',', '.')) > 0)}
            onClick={() => toList.mutate()}
          >
            {t('recipes.addToList')}
          </button>
        </div>
        {toList.data ? (
          <p role="status" data-testid="added">
            {t('recipes.addedToList', { count: toList.data.added.length })}
            {toList.data.already_listed.length
              ? ` ${t('recipes.alreadyListed', { names: toList.data.already_listed.join(', ') })}`
              : ''}
            {toList.data.in_stock.length
              ? ` ${t('recipes.inStock', { names: toList.data.in_stock.join(', ') })}`
              : ''}{' '}
            <Link to="/list">{t('recipes.toList')}</Link>
          </p>
        ) : null}
        <ErrorMessage error={toList.error ?? remove.error} />
        <div className="row wrap">
          <button type="button" onClick={onEdit}>
            {t('recipes.edit')}
          </button>
          {confirming ? (
            <button type="button" className="danger" onClick={() => remove.mutate()}>
              {t('recipes.confirmDelete')}
            </button>
          ) : (
            <button type="button" className="danger" onClick={() => setConfirming(true)}>
              {t('recipes.delete')}
            </button>
          )}
        </div>
      </div>
    </Sheet>
  )
}
