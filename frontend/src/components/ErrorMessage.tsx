import { useTranslation } from 'react-i18next'
import { ApiError } from '../api/client'

/** Shows a translated message for an API error code. */
export function ErrorMessage({ error }: { error: unknown }) {
  const { t } = useTranslation()
  if (!error) return null
  const code = error instanceof ApiError ? error.code : 'unknown'
  const detail = error instanceof ApiError ? error.detail : {}
  return (
    <p className="error" role="alert">
      {t(`errors.${code}`, { ...detail, defaultValue: t('errors.unknown') })}
    </p>
  )
}
