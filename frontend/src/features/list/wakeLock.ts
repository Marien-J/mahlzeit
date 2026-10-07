import { useEffect } from 'react'

type Sentinel = { release: () => Promise<void> }
type WakeLockApi = { request: (type: 'screen') => Promise<Sentinel> }

/** Keep the screen on while shopping. Browsers drop the lock when the tab hides; take it again. */
export function useWakeLock(on: boolean): void {
  useEffect(() => {
    const wakeLock = (navigator as Navigator & { wakeLock?: WakeLockApi }).wakeLock
    if (!on || !wakeLock) return
    let sentinel: Sentinel | null = null
    let active = true
    const acquire = () => {
      if (document.visibilityState !== 'visible') return
      wakeLock
        .request('screen')
        .then((s) => {
          if (active) sentinel = s
          else void s.release()
        })
        .catch(() => undefined)
    }
    acquire()
    document.addEventListener('visibilitychange', acquire)
    return () => {
      active = false
      document.removeEventListener('visibilitychange', acquire)
      void sentinel?.release().catch(() => undefined)
    }
  }, [on])
}
