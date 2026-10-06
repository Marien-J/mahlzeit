import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api, call, type Schemas } from '../../api/client'

export type Day = Schemas['DayOut']
export type PersonDay = Schemas['PersonDayOut']
export type Entry = Schemas['EntryOut']
export type ComponentIn = Schemas['ComponentIn']

export const dayKey = (day: string) => ['day', day] as const

export function useDay(day: string) {
  return useQuery({
    queryKey: dayKey(day),
    queryFn: () => call(api.GET('/api/days/{day_}', { params: { path: { day_: day } } })),
  })
}

/** Refetch every open day view after a change (entries can move between days). */
export function useRefreshDays() {
  const client = useQueryClient()
  return () => client.invalidateQueries({ queryKey: ['day'] })
}

export function logFood(body: Schemas['EntryIn']) {
  return call(api.POST('/api/entries', { body }))
}

export function updateEntry(id: string, body: Schemas['EntryPatchIn']) {
  return call(api.PATCH('/api/entries/{entry_id}', { params: { path: { entry_id: id } }, body }))
}

export function setEntryState(id: string, state: 'planned' | 'logged' | 'skipped') {
  return call(
    api.POST('/api/entries/{entry_id}/state', {
      params: { path: { entry_id: id } },
      body: { state },
    }),
  )
}

export function deleteEntry(id: string) {
  return call(api.DELETE('/api/entries/{entry_id}', { params: { path: { entry_id: id } } }))
}

export function copyEntry(id: string, day: string) {
  return call(
    api.POST('/api/entries/{entry_id}/copy', { params: { path: { entry_id: id } }, body: { day } }),
  )
}

export function copyDay(day: string, sourceDay: string) {
  return call(
    api.POST('/api/days/{day_}/copy', {
      params: { path: { day_: day } },
      body: { source_day: sourceDay },
    }),
  )
}

export function setDayType(day: string, dayType: 'training' | 'rest' | null) {
  return call(
    api.PUT('/api/days/{day_}/day-type', {
      params: { path: { day_: day } },
      body: { day_type: dayType },
    }),
  )
}

export function saveAsMeal(id: string, name?: string) {
  return call(
    api.POST('/api/entries/{entry_id}/save-as-meal', {
      params: { path: { entry_id: id } },
      body: { name: name ?? null },
    }),
  )
}
