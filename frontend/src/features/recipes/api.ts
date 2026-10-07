import { useQuery } from '@tanstack/react-query'
import { api, call, type Schemas } from '../../api/client'

export type { Recipe } from '../catalogue/api'
export type RecipeBody = Schemas['RecipeIn']
export type RecipePatch = Schemas['RecipePatchIn']
export type AddedToList = Schemas['AddedToListOut']

export function useRecipe(id: string | null) {
  return useQuery({
    queryKey: ['recipes', 'one', id],
    enabled: id !== null,
    queryFn: () =>
      call(api.GET('/api/recipes/{recipe_id}', { params: { path: { recipe_id: id ?? '' } } })),
  })
}

export function createRecipe(body: RecipeBody) {
  return call(api.POST('/api/recipes', { body }))
}

export function updateRecipe(id: string, body: RecipePatch) {
  return call(api.PATCH('/api/recipes/{recipe_id}', { params: { path: { recipe_id: id } }, body }))
}

export function deleteRecipe(id: string) {
  return call(api.DELETE('/api/recipes/{recipe_id}', { params: { path: { recipe_id: id } } }))
}

export function addToList(id: string, portions: number | null) {
  return call(
    api.POST('/api/recipes/{recipe_id}/add-to-list', {
      params: { path: { recipe_id: id } },
      body: { portions },
    }),
  )
}
