import { useTranslation } from 'react-i18next'
import { LANGUAGES, isLanguage, type Language } from '../i18n'
import { SelectField } from './Field'

export function LanguageSelect({
  value,
  onChange,
  disabled,
}: {
  value: string
  onChange: (language: Language) => void
  disabled?: boolean
}) {
  const { t } = useTranslation()
  return (
    <SelectField
      label={t('common.language')}
      value={value}
      disabled={disabled}
      options={LANGUAGES.map((l) => ({ value: l, label: t(`languages.${l}`) }))}
      onChange={(v) => {
        if (isLanguage(v)) onChange(v)
      }}
    />
  )
}
