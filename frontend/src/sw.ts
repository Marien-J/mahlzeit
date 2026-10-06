/// <reference lib="webworker" />
import { clientsClaim } from 'workbox-core'
import {
  cleanupOutdatedCaches,
  createHandlerBoundToURL,
  precacheAndRoute,
} from 'workbox-precaching'
import { NavigationRoute, registerRoute } from 'workbox-routing'

declare const self: ServiceWorkerGlobalScope & { __WB_MANIFEST: Array<string | { url: string }> }

self.skipWaiting()
clientsClaim()
cleanupOutdatedCaches()
precacheAndRoute(self.__WB_MANIFEST)

// The app shell answers every navigation, so the PWA opens offline. API calls are never cached here.
registerRoute(
  new NavigationRoute(createHandlerBoundToURL('index.html'), {
    denylist: [/^\/api\//, /^\/mcp/, /^\/events/],
  }),
)

type PushMessage = { title: string; body: string; url?: string; tag?: string }

self.addEventListener('push', (event) => {
  let message: PushMessage = { title: 'Mahlzeit', body: '' }
  try {
    message = { ...message, ...(event.data?.json() as Partial<PushMessage>) }
  } catch {
    message.body = event.data?.text() ?? ''
  }
  event.waitUntil(
    self.registration.showNotification(message.title, {
      body: message.body,
      icon: '/icons/icon-192.png',
      badge: '/icons/icon-192.png',
      tag: message.tag,
      data: { url: message.url ?? '/' },
    }),
  )
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const url = new URL(
    (event.notification.data as { url?: string })?.url ?? '/',
    self.location.origin,
  )
  event.waitUntil(
    (async () => {
      const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true })
      for (const client of windows) {
        if (new URL(client.url).origin === url.origin) {
          await client.focus()
          return client.navigate(url.href)
        }
      }
      return self.clients.openWindow(url.href)
    })(),
  )
})
