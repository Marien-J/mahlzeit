import { useTranslation } from 'react-i18next'
import { useSuggestions } from '../stock/api'
import type { ListFields, ListItem } from './model'

/**
 * Under the list: what planned meals need beyond stock, staples low or out, and usual purchases
 * that are not in stock. Nothing is added unless someone taps it.
 */
export function Suggested({
  items,
  onAdd,
}: {
  items: ListItem[]
  onAdd: (fields: ListFields) => void
}) {
  const { t } = useTranslation()
  const query = useSuggestions(navigator.onLine)
  const listed = new Set(items.map((i) => i.item_id).filter(Boolean))
  const shown = (query.data?.suggestions ?? []).filter((s) => !listed.has(s.item_id))
  if (!shown.length) return null
  return (
    <section className="aisle suggested" aria-label={t('suggested.title')}>
      <h2>{t('suggested.title')}</h2>
      <ul className="list-rows">
        {shown.map((s) => (
          <li key={s.item_id} className="list-row">
            <span className="what">
              <span>{s.name}</span>
              {s.quantity ? <span className="qty">{s.quantity}</span> : null}
              <small className={`reason ${s.reason}`}>
                {t(`suggested.reason.${s.reason}`, { count: query.data?.plan_days ?? 3 })}
              </small>
            </span>
            <button
              type="button"
              className="add-here"
              aria-label={t('suggested.add', { name: s.name })}
              onClick={() =>
                onAdd({
                  text: s.name,
                  item_id: s.item_id,
                  quantity: s.quantity,
                  category: s.category,
                  parse: false,
                })
              }
            >
              +
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}
