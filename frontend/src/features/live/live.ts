import { useQueryClient, type QueryKey } from '@tanstack/react-query'
import { useEffect, useSyncExternalStore } from 'react'

/**
 * Live updates from the server: one event stream per open app. An event names the kind of
 * thing that changed and the app refetches it; nothing else travels over the stream.
 */

// ['me'] is the signed-in user (meKey in auth/session; not imported, to keep imports acyclic).
const ME: QueryKey = ['me']

const KEYS: Record<string, QueryKey[]> = {
  list_item: [['list']],
  store: [['list']],
  meal_entry: [['day']],
  day_type: [['day']],
  targets: [['day'], ['targets']],
  item: [['items'], ['day']],
  favourite: [['items']],
  saved_meal: [['saved-meals']],
  household: [ME, ['household']],
  invite: [['household']],
  user: [ME, ['household'], ['day']],
  profile: [ME],
}

let connected = false
const listeners = new Set<() => void>()

function setConnected(value: boolean) {
  if (connected === value) return
  connected = value
  for (const listener of listeners) listener()
}

/** True while the event stream is open; the list falls back to polling otherwise. */
export function useLiveConnected(): boolean {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener)
      return () => listeners.delete(listener)
    },
    () => connected,
  )
}

export function keysFor(entity: string | null | undefined): QueryKey[] | 'all' {
  if (!entity || entity === '*') return 'all'
  return KEYS[entity] ?? []
}

/** Open the stream while signed in. `onReady` runs on every (re)connect. */
export function useLiveEvents(enabled: boolean, onReady?: () => void): void {
  const client = useQueryClient()
  useEffect(() => {
    if (!enabled || typeof EventSource === 'undefined') return
    const source = new EventSource('/api/events')
    const refetch = (keys: QueryKey[] | 'all') => {
      if (keys === 'all') void client.invalidateQueries()
      else for (const queryKey of keys) void client.invalidateQueries({ queryKey })
    }
    source.addEventListener('ready', () => {
      setConnected(true)
      // Whatever changed while the stream was down: fetch it now.
      refetch([['list'], ['day']])
      onReady?.()
    })
    source.addEventListener('change', (event) => {
      try {
        const data = JSON.parse((event as MessageEvent<string>).data) as { entity?: string }
        refetch(keysFor(data.entity))
      } catch {
        refetch('all')
      }
    })
    source.addEventListener('signed_out', () => {
      source.close()
      setConnected(false)
      void client.invalidateQueries({ queryKey: ME })
    })
    // The browser reconnects by itself (the server asks for 3 s); until then, poll.
    source.onerror = () => setConnected(false)
    return () => {
      source.close()
      setConnected(false)
    }
  }, [enabled, client, onReady])
}
