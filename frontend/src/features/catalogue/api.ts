import { useQuery } from '@tanstack/react-query'
import { api, call, type Schemas } from '../../api/client'

export type Item = Schemas['ItemOut']
export type Draft = Schemas['ItemDraftOut']
export type ItemIn = Schemas['ItemIn']
export type Recipe = Schemas['RecipeOut']
export type SavedMeal = Recipe

export function useItemSearch(query: string) {
  return useQuery({
    queryKey: ['items', query],
    queryFn: () => call(api.GET('/api/items', { params: { query: { q: query, limit: 25 } } })),
    placeholderData: (previous) => previous,
    staleTime: 30_000,
  })
}

export function useRecipes(kind?: Recipe['kind']) {
  return useQuery({
    queryKey: ['recipes', kind ?? 'all'],
    queryFn: () => call(api.GET('/api/recipes', { params: { query: kind ? { kind } : {} } })),
  })
}

/** One-serving recipes for one-tap logging. */
export function useSavedMeals() {
  return useRecipes('saved_meal')
}

export function lookupBarcode(code: string) {
  return call(api.GET('/api/barcodes/{code}', { params: { path: { code } } }))
}

export function searchOnline(q: string) {
  return call(api.GET('/api/online-search', { params: { query: { q } } }))
}

export function createItem(body: ItemIn) {
  return call(api.POST('/api/items', { body }))
}

export function updateItem(id: string, body: ItemIn) {
  return call(api.PUT('/api/items/{item_id}', { params: { path: { item_id: id } }, body }))
}

export function setFavourite(id: string, on: boolean) {
  return call(
    api.PUT('/api/items/{item_id}/favourite', { params: { path: { item_id: id } }, body: { on } }),
  )
}

/** The draft from Open Food Facts as a form value for the label form. */
export function draftToItemIn(d: Draft): ItemIn {
  return {
    names: d.names,
    brand: d.brand,
    category: d.category as ItemIn['category'],
    base_unit: d.base_unit,
    nutrients: d.nutrients,
    package_size: d.package_size,
    servings: d.servings,
    barcodes: d.barcode ? [d.barcode] : [],
    tracking_mode: 'counted',
    image_url: d.image_url,
    source: 'off',
  }
}

export function itemToItemIn(i: Item): ItemIn {
  return {
    names: i.names,
    brand: i.brand,
    category: i.category as ItemIn['category'],
    base_unit: i.base_unit,
    nutrients: i.nutrients,
    package_size: i.package_size,
    servings: i.servings,
    barcodes: i.barcodes,
    tracking_mode: i.tracking_mode,
    image_url: i.image_url,
    source: 'custom',
  }
}
