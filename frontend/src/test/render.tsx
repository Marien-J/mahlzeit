import { QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import { RouterProvider, createMemoryRouter } from 'react-router'
import { createQueryClient } from '../app/queryClient'
import { routes } from '../app/router'

export function renderApp(path: string) {
  const client = createQueryClient()
  client.setDefaultOptions({ queries: { retry: false } })
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  const result = render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
  return { ...result, router, client }
}
