import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { LanguageSelect } from '../../components/LanguageSelect'
import { setLanguage } from '../../i18n'

/** Frame for pages shown before sign-in, with a language switch. */
export function PublicLayout({ title, children }: { title: string; children: ReactNode }) {
  const { t, i18n } = useTranslation()
  return (
    <div className="public">
      <header className="public-header">
        <img src="/icons/icon-192.png" alt="" width={48} height={48} />
        <span className="brand">{t('app.name')}</span>
      </header>
      <main className="card">
        <h1>{title}</h1>
        {children}
      </main>
      <footer className="public-footer">
        <LanguageSelect value={i18n.language} onChange={(l) => void setLanguage(l)} />
      </footer>
    </div>
  )
}
