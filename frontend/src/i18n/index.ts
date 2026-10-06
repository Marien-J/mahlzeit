import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import de from './locales/de.json'
import en from './locales/en.json'
import nl from './locales/nl.json'

export const LANGUAGES = ['de', 'en', 'nl'] as const
export type Language = (typeof LANGUAGES)[number]
const STORAGE_KEY = 'mahlzeit.language'

export function isLanguage(value: unknown): value is Language {
  return typeof value === 'string' && (LANGUAGES as readonly string[]).includes(value)
}

/** Before sign-in: the last language used on this device, else the browser's, else German. */
export function detectLanguage(): Language {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (isLanguage(stored)) return stored
  } catch {
    // storage can be unavailable (private mode); fall through
  }
  for (const tag of navigator.languages ?? [navigator.language]) {
    const base = tag.slice(0, 2).toLowerCase()
    if (isLanguage(base)) return base
  }
  return 'de'
}

export async function setLanguage(language: Language): Promise<void> {
  if (i18n.language !== language) await i18n.changeLanguage(language)
  document.documentElement.lang = language
  try {
    localStorage.setItem(STORAGE_KEY, language)
  } catch {
    // ignore
  }
}

void i18n.use(initReactI18next).init({
  resources: { de: { translation: de }, en: { translation: en }, nl: { translation: nl } },
  lng: typeof navigator === 'undefined' ? 'de' : detectLanguage(),
  // Item names will fall back the same way: user language, then German, then English.
  fallbackLng: ['de', 'en'],
  interpolation: { escapeValue: false },
  returnNull: false,
})

if (typeof document !== 'undefined') document.documentElement.lang = i18n.language

export default i18n
