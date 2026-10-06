import { useTranslation } from 'react-i18next'

/** The favourite mark in front of a food name. */
export function Star() {
  const { t } = useTranslation()
  return (
    <span role="img" aria-label={t('foods.favourite')}>
      {t('foods.star')}{' '}
    </span>
  )
}
