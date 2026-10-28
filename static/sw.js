/* DER Studio — service worker: muestra el aviso cuando termina un trabajo y abre la app al tocarlo. */
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", e => e.waitUntil(self.clients.claim()));

self.addEventListener("push", e => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch (_) { d = { titulo: "DER Studio", texto: e.data && e.data.text() }; }
  e.waitUntil(self.registration.showNotification(d.titulo || "DER Studio", {
    body: d.texto || "",
    icon: "/icono-192.png",
    badge: "/icono-192.png",
    tag: d.url || "der-studio",
    data: { url: d.url || "/" },
  }));
});

self.addEventListener("notificationclick", e => {
  e.notification.close();
  const url = new URL(e.notification.data.url || "/", self.location.origin).href;
  e.waitUntil((async () => {
    const wins = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const w of wins) {
      if (new URL(w.url).origin === self.location.origin) {
        await w.focus();
        w.postMessage({ abrir: url });
        return;
      }
    }
    await self.clients.openWindow(url);
  })());
});
