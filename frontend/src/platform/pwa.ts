export async function registerServiceWorker() {
  if (typeof window === "undefined" || !("serviceWorker" in navigator)) {
    return;
  }

  if (import.meta.env.DEV) {
    window.addEventListener("load", () => {
      void clearDevelopmentServiceWorkers();
    });
    return;
  }

  window.addEventListener("load", () => {
    void registerProductionServiceWorker();
  });
}

async function clearDevelopmentServiceWorkers() {
  const registrations = await navigator.serviceWorker.getRegistrations();
  await Promise.all(registrations.map((registration) => registration.unregister()));
  if ("caches" in window) {
    const keys = await caches.keys();
    await Promise.all(keys.filter((key) => key.startsWith("ma-ipaas-")).map((key) => caches.delete(key)));
  }
}

async function registerProductionServiceWorker() {
  sessionStorage.removeItem("app-refreshing-for-update");
  const registration = await navigator.serviceWorker.register("/sw.js");
  await registration.update();

  registration.addEventListener("updatefound", () => {
    const installing = registration.installing;
    if (!installing) {
      return;
    }
    installing.addEventListener("statechange", () => {
      if (installing.state === "installed" && navigator.serviceWorker.controller) {
        installing.postMessage({ type: "SKIP_WAITING" });
      }
    });
  });

  navigator.serviceWorker.addEventListener("controllerchange", () => {
    if (sessionStorage.getItem("app-refreshing-for-update") === "1") {
      return;
    }
    sessionStorage.setItem("app-refreshing-for-update", "1");
    window.location.reload();
  });
}
