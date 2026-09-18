"""Middlewares : mur de connexion, en-têtes de sécurité, maintenance, contexte d'audit."""
from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import redirect, render, resolve_url
from django.urls import Resolver404, resolve
from django.utils import timezone

from core.models import Setting

CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; "
    "font-src 'self' data:; "
    "connect-src 'self'; "
    "frame-src 'self' data: blob:; "
    "manifest-src 'self'; "
    "worker-src 'self'; "
    "object-src 'none'; "
    "form-action 'self'; "
    "base-uri 'self'; "
    "frame-ancestors 'none'"
)
PERMISSIONS_POLICY = (
    "geolocation=(), camera=(), microphone=(), payment=(), usb=(), "
    "accelerometer=(), gyroscope=(), magnetometer=()"
)
# URL accessibles sans session (mur de connexion strict partout ailleurs)
PUBLIC_URLS = getattr(settings, "MDL_PUBLIC_URLS", ())


class RequireLoginMiddleware:
    """Exige une session pour toute URL non listée en public (aucun formulaire public)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        if not any(path.startswith(prefix) for prefix in PUBLIC_URLS):
            user = getattr(request, "user", None)
            if user is None or not user.is_authenticated:
                if path.startswith("/api/") or request.headers.get("x-requested-with") == "fetch":
                    return HttpResponse("{}", status=401, content_type="application/json")
                return redirect("%s?next=%s" % (resolve_url(settings.LOGIN_URL), path))
            if getattr(user, "must_change_password", False) and path != "/connexion/bienvenue/":
                try:
                    match = resolve(path)
                except Resolver404:
                    match = None
                if match is None or match.url_name not in {"welcome", "logout", "theme_css", "manifest",
                                                            "service_worker", "offline"}:
                    return redirect("auth:welcome")
            if getattr(user, "must_accept_charte", False) and path != "/connexion/bienvenue/":
                try:
                    match = resolve(path)
                except Resolver404:
                    match = None
                if match is None or match.url_name not in {"welcome", "logout", "theme_css", "manifest",
                                                            "service_worker", "offline"}:
                    return redirect("auth:welcome")
            # Le rôle peut imposer l'A2F : l'inscription est demandée dès la
            # première connexion. Tant que le délai court, le membre peut
            # reporter ; passé le délai, l'écran d'activation est obligatoire.
            if getattr(user, "two_factor_pending", False):
                exemptes = {"twofa_setup", "twofa", "twofa_disable", "logout", "welcome",
                            "theme_css", "manifest", "service_worker", "offline"}
                try:
                    match = resolve(path)
                except Resolver404:
                    match = None
                if match is None or match.url_name not in exemptes:
                    report = request.session.get("twofa_deferred")
                    if user.two_factor_overdue or not report:
                        return redirect("auth:twofa_setup")
            now = timezone.now()
            previous = user.last_seen
            if previous is None or (now - previous) > timedelta(minutes=5):
                user.last_seen = now
                user._meta.concrete_model.objects.filter(pk=user.pk).update(last_seen=now)
        return self.get_response(request)


class SecurityHeadersMiddleware:
    """CSP, HSTS et en-têtes durcis (pas de COOP/COEP : viewer PDF et push en ont besoin)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response["X-Frame-Options"] = "DENY"
        response["Referrer-Policy"] = "same-origin"
        response["X-Content-Type-Options"] = "nosniff"
        response["Permissions-Policy"] = PERMISSIONS_POLICY
        csp = CSP if settings.DEBUG else CSP + "; upgrade-insecure-requests"
        response["Content-Security-Policy"] = csp
        response["Cross-Origin-Opener-Policy"] = "same-origin-allow-popups"
        if not settings.DEBUG:
            response["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


class MaintenanceModeMiddleware:
    """Mode maintenance : message + liste des comptes exclus."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        active = settings.MAINTENANCE
        message = settings.MAINTENANCE_MESSAGE
        excluded = []
        try:
            app = Setting.data().get("app", {})
            active = active or bool(app.get("maintenance"))
            message = message or app.get("maintenance_message") or ""
            excluded = app.get("exclus_maintenance") or []
        except Exception:
            pass
        user = getattr(request, "user", None)
        is_excluded = bool(user and getattr(user, "is_authenticated", False) and (
            user.email in excluded or getattr(user, "is_administrator_flag", False)
        ))
        if active and not is_excluded and request.path not in ("/sante/", "/static/"):
            if request.path.startswith("/static/") or request.path.startswith("/theme.css"):
                return self.get_response(request)
            return render(request, "core/maintenance.html", {"message": message}, status=503)
        return self.get_response(request)


class AuditContextMiddleware:
    """Expose IP + user-agent au journal d'audit (écrit par audit.services)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.client_ip = (
            request.headers.get("x-forwarded-for", "").split(",")[0].strip()
            or request.META.get("REMOTE_ADDR", "")
        )
        request.user_agent = request.headers.get("user-agent", "")[:240]
        request.origin = "web"
        return self.get_response(request)
