import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Sheet } from '../../components/Sheet'
import { kcal } from '../../lib/nutrition'
import { useItemSearch, type Item } from '../catalogue/api'

/** Search the catalogue and pick one food (the amount is set in the recipe). */
export function IngredientPicker({
  onPick,
  onClose,
}: {
  onPick: (item: Item) => void
  onClose: () => void
}) {
  const { t } = useTranslation()
  const [query, setQuery] = useState('')
  const found = useItemSearch(query)
  return (
    <Sheet title={t('recipes.addIngredient')} onClose={onClose}>
      <div className="stack">
        <label className="field">
          <span>{t('recipes.searchIngredient')}</span>
          <input
            type="search"
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            autoComplete="off"
          />
        </label>
        <ul className="list results">
          {(found.data ?? []).map((item) => (
            <li key={item.id}>
              <button type="button" className="result" onClick={() => onPick(item)}>
                <span>
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
      </div>
    </Sheet>
  )
}
