import { useSyncExternalStore } from 'react'
import { useTranslation } from 'react-i18next'

function subscribe(callback: () => void) {
  window.addEventListener('online', callback)
  window.addEventListener('offline', callback)
  return () => {
    window.removeEventListener('online', callback)
    window.removeEventListener('offline', callback)
  }
}

export function useOnline(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => navigator.onLine,
    () => true,
  )
}

export function OfflineBanner() {
  const { t } = useTranslation()
  if (useOnline()) return null
  return (
    <div className="offline" role="status">
      {t('app.offline')}
    </div>
  )
}
