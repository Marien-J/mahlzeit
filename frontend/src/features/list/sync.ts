import { useQuery, type QueryClient } from '@tanstack/react-query'
import { useEffect, useSyncExternalStore } from 'react'
import { ApiError, api, call, type Schemas } from '../../api/client'
import { useLiveConnected } from '../live/live'
import type { Memory, Op } from './model'

/**
 * The list works offline: every change goes into an outbox kept in localStorage, is shown at
 * once (model.applyOps), and is sent in order whenever the server can be reached. Each change
 * carries the item's own id and the time it was made, so sending twice never duplicates.
 */

export type ListData = Schemas['ListOut']
export const listKey = ['list'] as const
export const historyKey = ['list', 'history'] as const
const OUTBOX_KEY = 'mahlzeit.outbox'
const LIST_KEY = 'mahlzeit.list'
const HISTORY_KEY = 'mahlzeit.list.history'
const BATCH = 200
const POLL_MS = 15_000
const RETRY_MS = 10_000

type Saved<T> = { household: string; value: T }

function read<T>(key: string, household: string): T | undefined {
  try {
    const raw = localStorage.getItem(key)
    if (!raw) return undefined
    const saved = JSON.parse(raw) as Saved<T>
    return saved.household === household ? saved.value : undefined
  } catch {
    return undefined
  }
}

function write<T>(key: string, household: string, value: T): void {
  try {
    localStorage.setItem(key, JSON.stringify({ household, value } satisfies Saved<T>))
  } catch {
    // storage full or blocked: the list still works while the page is open
  }
}

/** Forget everything kept for offline use (on sign-out). */
export function forgetOfflineList(): void {
  try {
    for (const key of [OUTBOX_KEY, LIST_KEY, HISTORY_KEY]) localStorage.removeItem(key)
  } catch {
    // nothing kept
  }
  outbox = { household: null, ops: [] }
  emit()
}

// --- outbox ----------------------------------------------------------------------------------

let outbox: { household: string | null; ops: Op[] } = { household: null, ops: [] }
const listeners = new Set<() => void>()

function emit() {
  for (const listener of listeners) listener()
}

function load(household: string) {
  if (outbox.household === household) return
  outbox = { household, ops: read<Op[]>(OUTBOX_KEY, household) ?? [] }
}

function save() {
  if (outbox.household) write(OUTBOX_KEY, outbox.household, outbox.ops)
  emit()
}

export function useOutbox(household: string): Op[] {
  load(household)
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener)
      return () => listeners.delete(listener)
    },
    () => outbox.ops,
  )
}

export function enqueue(household: string, op: Omit<Op, 'at'> & { at?: string }): void {
  load(household)
  outbox = { household, ops: [...outbox.ops, { ...op, at: op.at ?? new Date().toISOString() }] }
  save()
}

/** Changes still waiting to be sent. */
export function pendingCount(household: string): number {
  load(household)
  return outbox.ops.length
}

let inflight: Promise<void> | null = null
let again = false

/** Send queued changes in order. One flush at a time; changes queued meanwhile follow. */
export function flush(client: QueryClient, household: string): Promise<void> {
  load(household)
  if (inflight) {
    again = true
    return inflight
  }
  inflight = (async () => {
    do {
      again = false
      const batch = outbox.ops.slice(0, BATCH)
      if (batch.length === 0) break
      try {
        const result = await call(api.POST('/api/list/ops', { body: { ops: batch } }))
        drop(batch.length)
        client.setQueryData(listKey, result.list)
        write(LIST_KEY, household, result.list)
        void client.invalidateQueries({ queryKey: historyKey })
        again = again || outbox.ops.length > 0
      } catch (err) {
        // A batch the server cannot read would block the queue forever: drop it. Anything
        // else (offline, server down, signed out) waits for the next try.
        if (err instanceof ApiError && err.status === 422) {
          drop(batch.length)
          again = true
        } else break
      }
    } while (again)
  })().finally(() => {
    inflight = null
  })
  return inflight
}

function drop(count: number) {
  outbox = { ...outbox, ops: outbox.ops.slice(count) }
  save()
}

// --- queries ---------------------------------------------------------------------------------

/** The list from the server, cached on the phone so a repeat visit shows it at once. */
export function useListQuery(household: string) {
  const live = useLiveConnected()
  return useQuery({
    queryKey: listKey,
    queryFn: async () => {
      const list = await call(api.GET('/api/list'))
      write(LIST_KEY, household, list)
      return list
    },
    initialData: () => read<ListData>(LIST_KEY, household),
    initialDataUpdatedAt: 0,
    // Live events make polling unnecessary; without them, poll.
    refetchInterval: live ? false : POLL_MS,
  })
}

export function useHistory(household: string) {
  return useQuery({
    queryKey: historyKey,
    queryFn: async (): Promise<Memory[]> => {
      const history = await call(api.GET('/api/list/history'))
      write(HISTORY_KEY, household, history)
      return history
    },
    initialData: () => read<Memory[]>(HISTORY_KEY, household),
    initialDataUpdatedAt: 0,
    staleTime: 5 * 60_000,
  })
}

/** Keep the outbox moving: now, when the connection returns, and every few seconds. */
export function useOutboxSender(client: QueryClient, household: string, pending: number): void {
  useEffect(() => {
    const send = () => void flush(client, household)
    send()
    window.addEventListener('online', send)
    const timer = pending > 0 ? window.setInterval(send, RETRY_MS) : undefined
    return () => {
      window.removeEventListener('online', send)
      if (timer) window.clearInterval(timer)
    }
  }, [client, household, pending])
}
