import { useQuery } from '@tanstack/react-query'
import { api, call, type Schemas } from '../../api/client'

export type Plan = Schemas['PlanOut']
export type PlanDay = Schemas['PlanDayOut']

export const planKey = (start: string, days: number) => ['plan', start, days] as const

/** Every entry of the household from `start` for `days` days, with the open offers. */
export function usePlan(start: string, days: number) {
  return useQuery({
    queryKey: planKey(start, days),
    // Showing more days keeps the days already there while the rest loads.
    placeholderData: (previous) => previous,
    queryFn: () => call(api.GET('/api/plan', { params: { query: { start, days } } })),
  })
}
