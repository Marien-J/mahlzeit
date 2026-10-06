import { useSyncExternalStore } from 'react'

type InstallPrompt = Event & {
  prompt: () => Promise<void>
  userChoice: Promise<{ outcome: string }>
}

let deferred: InstallPrompt | null = null
const listeners = new Set<() => void>()
const notify = () => listeners.forEach((l) => l())

/** Call once at startup: keeps Chrome's install prompt for the settings button. */
export function captureInstallPrompt(): void {
  window.addEventListener('beforeinstallprompt', (event) => {
    event.preventDefault()
    deferred = event as InstallPrompt
    notify()
  })
  window.addEventListener('appinstalled', () => {
    deferred = null
    notify()
  })
}

export function isStandalone(): boolean {
  return window.matchMedia?.('(display-mode: standalone)').matches ?? false
}

export function useInstallPrompt() {
  const available = useSyncExternalStore(
    (cb) => {
      listeners.add(cb)
      return () => listeners.delete(cb)
    },
    () => deferred !== null,
    () => false,
  )
  return {
    available,
    installed: isStandalone(),
    async install() {
      if (!deferred) return
      await deferred.prompt()
      await deferred.userChoice
      deferred = null
      notify()
    },
  }
}
