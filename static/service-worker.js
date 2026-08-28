// TRUST CRM — service worker mínimo.
//
// O que ISSO NÃO é: suporte a uso offline do CRM. O Streamlit mantém uma
// conexão WebSocket viva com o servidor para cada interação (clique,
// digitação, navegação) — sem essa conexão a tela simplesmente não
// funciona. Nenhum service worker consegue simular isso client-side.
//
// O Streamlit também só permite hospedar arquivos estáticos dentro da
// pasta "static/" (servida em "/app/static/..."), então o navegador só
// concede a este arquivo controle sobre esse mesmo caminho — não sobre
// o app inteiro (que vive em "/"). Ou seja, este service worker só pode
// cachear os arquivos estáticos dele mesmo (ícones, manifest.json).
//
// Para que serve, então: permitir que o Chrome/Android considere o CRM
// "instalável" como PWA (ícone na tela inicial, abre em janela própria,
// sem barra de endereço) e deixar os ícones/manifest disponíveis mais
// rápido em acessos repetidos. Nada além disso.

const CACHE_NAME = "trust-crm-static-v1";
const PRECACHE_URLS = [
  "./manifest.json",
  "./icons/icon-192.png",
  "./icons/icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE_NAME)
      .then((cache) => cache.addAll(PRECACHE_URLS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((names) =>
        Promise.all(
          names
            .filter((name) => name !== CACHE_NAME)
            .map((name) => caches.delete(name))
        )
      )
      .then(() => self.clients.claim())
  );
});

// Network-first: sempre tenta buscar a versão atual; só usa o cache como
// reserva se a rede falhar (por exemplo, um instante sem conexão).
self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;

  event.respondWith(
    fetch(event.request)
      .then((response) => {
        const copy = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
        return response;
      })
      .catch(() => caches.match(event.request))
  );
});
