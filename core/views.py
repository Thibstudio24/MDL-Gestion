"""Vues de service : tableau de bord, thème, PWA, médias privés, erreurs, textes légaux."""
from __future__ import annotations

import mimetypes
from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse, HttpResponseNotFound, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.cache import never_cache

from core import permissions, theme
from core.dashboard import build_sections
from core.models import LegalDocument, SchoolYear, Setting
from core.rich import render as render_markdown
from core.services import health as health_payload


@login_required
def dashboard(request):
    """Tableau de bord : tuiles prédéfinies, jamais vides, filtrées par droits."""
    sections = build_sections(request.user)
    year = SchoolYear.current()
    return render(request, "core/dashboard.html", {
        "sections": sections,
        "page_title": "Tableau de bord",
        "current_year": year,
    })


# --------------------------------------------------------------------------- #
# Thème / PWA
# --------------------------------------------------------------------------- #
@never_cache
def theme_css(request):
    """Feuille de thème générée dynamiquement (aucune authentification requise)."""
    palette = request.GET.get("palette") or "ardoise"
    seed = request.GET.get("seed") or ""
    forced = {}
    try:
        forced = Setting.forced_theme()
        seed = seed or forced.get("seed") or ""
    except Exception:
        forced = {}
    css = theme.build_css(palette, seed)
    return HttpResponse(css, content_type="text/css; charset=utf-8")


@never_cache
def manifest(request):
    brand = Setting.brand()
    nom = brand.get("nom") or "MDL"
    palette_name = brand.get("palette_imposee") or Setting.theme().get("palette") or "ardoise"
    seed = brand.get("couleur_principale") or "#33556e"
    primary = theme.palette(palette_name, seed)[ "light"]["primary"]
    icons = [
        {"src": "/static/icons/app-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
        {"src": "/static/icons/app-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
        {"src": "/static/icons/maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
    ]
    shortcuts = [
        {"name": "Tableau de bord", "short_name": "Accueil", "url": "/", "icons": [icons[0]]},
        {"name": "Trésorerie", "short_name": "Trésorerie", "url": "/tresorerie/", "icons": [icons[0]]},
        {"name": "Mon planning", "short_name": "Planning", "url": "/planning/mes-disponibilites/", "icons": [icons[0]]},
        {"name": "Messages", "short_name": "Messages", "url": "/messages/", "icons": [icons[0]]},
    ]
    payload = {
        "name": nom,
        "short_name": (brand.get("sigle") or nom)[:12],
        "description": "Gestion de la Maison des Lycéens — %s" % (brand.get("lycee") or ""),
        "lang": "fr",
        "dir": "ltr",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "orientation": "any",
        "theme_color": primary,
        "background_color": "#ffffff",
        "categories": ["education", "productivity"],
        "icons": icons,
        "shortcuts": shortcuts,
    }
    return JsonResponse(payload, content_type="application/manifest+json; charset=utf-8",
                        json_dumps_params={"ensure_ascii": False, "indent": 2})


SERVICE_WORKER = r"""/* MDL Gestion — service worker (coquille + lecture hors ligne) */
const VERSION = '__VERSION__';
const SHELL = 'mdl-shell-' + VERSION;
const PAGES = 'mdl-pages-' + VERSION;
const SHELL_FILES = [
  '/static/css/app.css',
  '/static/js/app.js',
  '/static/js/grid.js',
  '/static/js/prefs.js',
  '/static/vendor/chart.umd.min.js',
  '/static/icons/app-192.png',
  '/static/icons/app-512.png',
  '/static/icons/favicon.svg',
  '/theme.css',
  '/hors-ligne/'
];
const CACHEABLE = ['/', '/documents/', '/planning/', '/menage/', '/messages/', '/tresorerie/'];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(SHELL).then((cache) => cache.addAll(SHELL_FILES).catch(() => null))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(
      keys.filter((k) => k !== SHELL && k !== PAGES).map((k) => caches.delete(k))
    )).then(() => self.clients.claim())
  );
});

self.addEventListener('message', (event) => {
  if (event.data === 'skip-waiting') self.skipWaiting();
  if (event.data === 'clear-cache') {
    event.waitUntil(caches.keys().then((keys) => Promise.all(keys.map((k) => caches.delete(k)))));
  }
});

const isCacheable = (url) => {
  if (url.pathname.startsWith('/static/')) return true;
  return CACHEABLE.some((path) => url.pathname === path || url.pathname.startsWith(path));
};

self.addEventListener('fetch', (event) => {
  const request = event.request;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const copy = response.clone();
          if (isCacheable(url)) caches.open(PAGES).then((c) => c.put(request, copy));
          return response;
        })
        .catch(() => caches.match(request).then((hit) => hit || caches.match('/hors-ligne/')))
    );
    return;
  }
  // Réseau d'abord, repli « last-known »
  event.respondWith(
    fetch(request)
      .then((response) => {
        if (response && response.status === 200 && isCacheable(url)) {
          const copy = response.clone();
          caches.open(PAGES).then((c) => c.put(request, copy));
        }
        return response;
      })
      .catch(() => caches.match(request).then((hit) => hit || Response.error()))
  );
});

self.addEventListener('push', (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch (e) { data = { title: 'MDL', body: event.data ? event.data.text() : '' }; }
  event.waitUntil(self.registration.showNotification(data.title || 'MDL Gestion', {
    body: data.body || '',
    icon: '/static/icons/app-192.png',
    badge: '/static/icons/badge-72.png',
    tag: data.tag || 'mdl',
    data: { url: data.url || '/' },
    lang: 'fr'
  }));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const target = (event.notification.data && event.notification.data.url) || '/';
  event.waitUntil(clients.matchAll({ type: 'window' }).then((list) => {
    for (const client of list) {
      if ('focus' in client) return client.focus().then((c) => c.navigate(target));
    }
    return clients.openWindow(target);
  }));
});
"""


@never_cache
def service_worker(request):
    body = SERVICE_WORKER.replace("__VERSION__", getattr(settings, "VERSION", "1.0.0"))
    response = HttpResponse(body, content_type="application/javascript; charset=utf-8")
    response["Service-Worker-Allowed"] = "/"
    return response


def offline(request):
    return render(request, "core/offline.html", {"page_title": "Hors ligne"})


@never_cache
def health(request):
    return JsonResponse(health_payload())


@never_cache
def favicon(request):
    path = Path(settings.BASE_DIR) / "static" / "icons" / "favicon.svg"
    if not path.exists():
        return HttpResponseNotFound()
    return HttpResponse(path.read_bytes(), content_type="image/svg+xml")


@never_cache
def robots(request):
    return HttpResponse("User-agent: *\nDisallow: /\n", content_type="text/plain; charset=utf-8")


def serve_media(request, relpath: str):
    """Média privé : vérifie les droits du module concerné (jamais public en production).

    Passe par le stockage par défaut : disque du serveur ou fournisseur S3.
    """
    from django.core.files.storage import default_storage

    name = relpath.lstrip("/")
    if ".." in name.split("/") or name.startswith("/"):
        raise PermissionDenied()
    if not default_storage.exists(name):
        return HttpResponseNotFound()
    module = _module_for(name)
    if module and not permissions.can_view(request.user, module):
        raise PermissionDenied()
    filename = name.rsplit("/", 1)[-1]
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    with default_storage.open(name, "rb") as handle:
        response = HttpResponse(handle.read(), content_type=content_type)
    response["Content-Disposition"] = 'inline; filename="%s"' % filename
    response["X-Content-Type-Options"] = "nosniff"
    return response


def _module_for(path: str) -> str:
    if path.startswith("documents/"):
        return "documents"
    if path.startswith("finance/"):
        return "finance"
    if path.startswith("chores/"):
        return "planning_menage"
    if path.startswith("plannings/"):
        return "planning_salle"
    if path.startswith("mail/"):
        return "mail"
    if path.startswith("avatars/"):
        return ""
    return "dashboard"


# --------------------------------------------------------------------------- #
# Textes légaux
# --------------------------------------------------------------------------- #
def legal(request, slug: str):
    document = get_object_or_404(LegalDocument, slug=slug, published=True)
    return render(request, "core/legal.html", {
        "document": document,
        "html": render_markdown(document.body),
        "page_title": document.title,
    })


# --------------------------------------------------------------------------- #
# Erreurs
# --------------------------------------------------------------------------- #
def error_403(request, exception=None):
    return render(request, "core/403.html", {"exception": exception, "page_title": "Accès refusé"}, status=403)


def error_404(request, exception=None):
    return render(request, "core/404.html", {"exception": exception, "page_title": "Page introuvable"}, status=404)


def error_500(request):
    return render(request, "core/500.html", {"page_title": "Erreur serveur"}, status=500)
