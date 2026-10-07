import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { ErrorMessage } from '../../components/ErrorMessage'
import { Field, Toggle } from '../../components/Field'
import { Sheet } from '../../components/Sheet'
import { type Item, type Recipe } from '../catalogue/api'
import { createRecipe, updateRecipe } from './api'
import { IngredientPicker } from './IngredientPicker'

type Row = { item_id: string; name: string; unit: string; amount: string }

const number = (text: string): number => Number(text.replace(',', '.'))

/** Create a recipe, or change one: servings, cooked yield, staple, notes and the ingredients. */
export function RecipeEditor({
  recipe,
  onDone,
  onClose,
}: {
  recipe: Recipe | null
  onDone: (saved: Recipe) => void
  onClose: () => void
}) {
  const { t } = useTranslation()
  const [name, setName] = useState(recipe?.name ?? '')
  const [servings, setServings] = useState(String(recipe?.servings ?? 2))
  const [cooked, setCooked] = useState(
    recipe?.cooked_yield_g != null ? String(recipe.cooked_yield_g) : '',
  )
  const [staple, setStaple] = useState(recipe?.staple ?? false)
  const [notes, setNotes] = useState(recipe?.notes ?? '')
  const [rows, setRows] = useState<Row[]>(
    (recipe?.ingredients ?? []).map((i) => ({
      item_id: i.item_id,
      name: i.name,
      unit: i.base_unit,
      amount: String(i.amount),
    })),
  )
  const [picking, setPicking] = useState(false)
  const client = useQueryClient()

  const valid =
    name.trim() !== '' &&
    number(servings) > 0 &&
    rows.length > 0 &&
    rows.every((r) => number(r.amount) > 0)
  const save = useMutation({
    mutationFn: () => {
      const body = {
        name: name.trim(),
        servings: number(servings),
        cooked_yield_g: cooked.trim() === '' ? null : number(cooked),
        staple,
        notes: notes.trim() === '' ? null : notes.trim(),
        ingredients: rows.map((r) => ({ item_id: r.item_id, amount: number(r.amount) })),
      }
      return recipe ? updateRecipe(recipe.id, body) : createRecipe({ ...body, kind: 'recipe' })
    },
    onSuccess: async (saved) => {
      await client.invalidateQueries({ queryKey: ['recipes'] })
      onDone(saved)
    },
  })
  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (valid) save.mutate()
  }
  const add = (item: Item) => {
    setRows((current) => [
      ...current,
      { item_id: item.id, name: item.name, unit: item.base_unit, amount: '100' },
    ])
    setPicking(false)
  }

  return (
    <Sheet title={recipe ? t('recipes.edit') : t('recipes.new')} onClose={onClose}>
      <form className="stack" onSubmit={submit}>
        <Field
          label={t('meals.name')}
          value={name}
          required
          maxLength={120}
          onChange={(e) => setName(e.target.value)}
        />
        <div className="row">
          <Field
            label={t('recipes.servings')}
            inputMode="decimal"
            value={servings}
            onChange={(e) => setServings(e.target.value)}
          />
          <Field
            label={t('recipes.cookedYield')}
            inputMode="decimal"
            value={cooked}
            hint={t('recipes.cookedYieldHint')}
            onChange={(e) => setCooked(e.target.value)}
          />
        </div>
        <Toggle label={t('recipes.staple')} checked={staple} onChange={setStaple} />
        <label className="field">
          <span>{t('recipes.notes')}</span>
          <textarea
            rows={3}
            maxLength={4000}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
          />
        </label>
        <h3>{t('recipes.ingredients')}</h3>
        {rows.length === 0 ? <p className="muted">{t('recipes.noIngredients')}</p> : null}
        <ul className="list compact">
          {rows.map((row, index) => (
            <li key={`${row.item_id}-${index}`} className="row spread">
              <span>{row.name}</span>
              <label className="amount">
                <input
                  inputMode="decimal"
                  aria-label={t('log.amountOf', { name: row.name })}
                  value={row.amount}
                  onChange={(e) =>
                    setRows((current) =>
                      current.map((r, i) => (i === index ? { ...r, amount: e.target.value } : r)),
                    )
                  }
                />
                {row.unit}
              </label>
              <button
                type="button"
                className="icon"
                aria-label={t('recipes.removeIngredient', { name: row.name })}
                onClick={() => setRows((current) => current.filter((_, i) => i !== index))}
              >
                ×
              </button>
            </li>
          ))}
        </ul>
        <button type="button" onClick={() => setPicking(true)}>
          {t('recipes.addIngredient')}
        </button>
        <ErrorMessage error={save.error} />
        <button type="submit" className="primary" disabled={!valid || save.isPending}>
          {t('common.save')}
        </button>
      </form>
      {picking ? <IngredientPicker onPick={add} onClose={() => setPicking(false)} /> : null}
    </Sheet>
  )
}
