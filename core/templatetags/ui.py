"""Filtres et balises d'interface (formats FR, pagination, badges)."""
from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation

from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _

register = template.Library()


@register.filter
def money(value) -> str:
    """1 250,50 € — format français."""
    try:
        amount = Decimal(str(value or 0)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return "0,00 €"
    negative = amount < 0
    text = "{:,.2f}".format(abs(amount)).replace(",", "\u202f").replace(".", ",")
    return "%s%s €" % ("−" if negative else "", text)


@register.filter
def number_fr(value) -> str:
    try:
        amount = Decimal(str(value or 0))
    except (InvalidOperation, ValueError, TypeError):
        return "0"
    text = "{:,}".format(amount).replace(",", "\u202f")
    return text


@register.filter
def signed_money(value) -> str:
    try:
        amount = Decimal(str(value or 0))
    except (InvalidOperation, ValueError, TypeError):
        return "0,00 €"
    prefix = "+" if amount > 0 else ""
    return prefix + money(amount)


@register.filter
def percent(value) -> str:
    try:
        return "{:.0f} %".format(float(value or 0))
    except (TypeError, ValueError):
        return "0 %"


@register.filter
def date_fr(value, fmt: str = "%d/%m/%Y") -> str:
    if not value:
        return "—"
    try:
        return value.strftime(fmt)
    except (AttributeError, ValueError):
        return str(value)


@register.filter
def duration_fr(value) -> str:
    if not value:
        return "—"
    total = int(value.total_seconds() // 60)
    if total < 60:
        return _("%s min") % total
    hours, minutes = divmod(total, 60)
    if hours < 24:
        return _("%(h)s h %(m)s") % {"h": hours, "m": minutes}
    return _("%s j") % (hours // 24)


@register.filter
def get_item(d, key):
    try:
        return (d or {}).get(key)
    except AttributeError:
        return None


@register.filter
def as_json(value) -> str:
    """JSON pour un attribut HTML : renvoyé non marqué sûr, Django l'échappe à l'affichage."""
    return json.dumps(value, ensure_ascii=False, default=str)


@register.filter
def initials(user) -> str:
    first = (getattr(user, "first_name", "") or "?")[:1].upper()
    last = (getattr(user, "last_name", "") or "")[:1].upper()
    return first + last


@register.simple_tag
def level_badge(level_value: int) -> str:
    labels = {0: "Aucun", 1: "Consulter", 2: "Modifier"}
    css = {0: "muted", 1: "info", 2: "success"}
    label = labels.get(int(level_value or 0), "?")
    return format_html('<span class="badge badge-{}">{}</span>', css.get(int(level_value or 0), "muted"), label)


@register.inclusion_tag("partials/_pagination.html", takes_context=True)
def pagination(context, page_obj):
    return {
        "page_obj": page_obj,
        "paginator": getattr(page_obj, "paginator", None),
        "query": context.get("query", ""),
        "base_url": context.get("base_url", context["request"].path),
    }


@register.inclusion_tag("partials/_tile.html")
def tile(tile_data):
    return {"tile": tile_data}


@register.simple_tag
def status_badge(status: str, label: str = "") -> str:
    mapping = {
        "pending": "warning", "active": "success", "inactive": "muted", "anonymized": "muted",
        "draft": "muted", "open": "info", "closed": "muted", "published": "success",
        "sent": "success", "failed": "danger", "queued": "warning", "sending": "info",
        "skipped": "muted", "todo": "muted", "done": "info", "validated": "success", "redo": "danger",
        "applied": "success", "revoked": "muted", "delivered": "info",
    }
    css = mapping.get(str(status), "muted")
    return format_html('<span class="badge badge-{}">{}</span>', css, label or status)


@register.filter
def add_query(url: str, pairs: str) -> str:
    """Ajoute des paramètres à une URL : ``url|add_query:"page=2&q=x"``."""
    if not pairs:
        return url
    sep = "&" if "?" in url else "?"
    return "%s%s%s" % (url, sep, pairs)


@register.filter
def kb(size) -> str:
    try:
        size = float(size or 0)
    except (TypeError, ValueError):
        return "0 Ko"
    for unit in ("o", "Ko", "Mo", "Go"):
        if size < 1024 or unit == "Go":
            return "%s %s" % (("{:,.1f}".format(size).replace(",", "\u202f").replace(".", ",")).rstrip("0").rstrip(","), unit)
        size /= 1024
    return "%s Go" % size


@register.simple_tag
def icon(name: str, size: int = 16) -> str:
    from core.icons import svg_icon

    # Le nom vient des gabarits (jeu d'icônes interne), jamais d'une saisie utilisateur.
    return mark_safe(svg_icon(name, size))  # nosec B308 B703


@register.simple_tag(takes_context=False)
def static_path(relative: str) -> str:
    from django.conf import settings
    from django.templatetags.static import static

    try:
        return static(relative)
    except Exception:  # staticfiles non collecté (premier lancement)
        return "%s%s" % (settings.STATIC_URL, relative)


@register.filter
def mapfield(items, key: str):
    """Extrait une clé d'une liste de dictionnaires (valeurs JSON-friendly pour les graphiques)."""
    from decimal import Decimal as _Decimal

    if not items:
        return []
    values = []
    for item in items:
        try:
            value = item[key] if isinstance(item, dict) else getattr(item, key, "")
        except (KeyError, TypeError):
            value = ""
        if isinstance(value, _Decimal):
            value = float(value)
        values.append(value)
    return values


@register.filter
def markdown(value):
    """Rendu Markdown léger (titres, gras, listes, liens) pour les messages du bureau.

    Le HTML brut est échappé avant conversion : une balise saisie dans un message
    reste du texte, jamais du code exécuté (XSS).
    """
    if not value:
        return mark_safe("")  # nosec B308 B703 - chaîne vide
    from django.utils.html import escape

    source = escape(str(value))
    try:
        import markdown as _markdown

        html = _markdown.markdown(source, extensions=["nl2br", "sane_lists"], output_format="html5")
    except Exception:  # pragma: no cover - repli texte brut si la lib manque
        html = "<p>%s</p>" % source.replace("\n", "<br>")
    # La source est échappée ci-dessus : aucune balise brute ne survit.
    return mark_safe(html)  # nosec B308 B703


@register.simple_tag
def histogram_chart(rows, income_label="Recettes", expense_label="Dépenses"):
    """Spécification Chart.js de l'histogramme mensuel (recettes positives, dépenses négatives)."""
    rows = rows or []
    return {
        "type": "bar",
        "labels": [row.get("label", "") for row in rows],
        "series": [
            {"label": income_label, "data": [row.get("income_value", 0) for row in rows], "css": "success"},
            {"label": expense_label, "data": [row.get("expense_value", 0) for row in rows], "css": "danger"},
        ],
    }


@register.simple_tag
def donut_chart(rows, label_key="label", value_key="total"):
    """Spécification Chart.js d'un anneau (répartition par catégorie)."""
    rows = rows or []
    values = []
    for row in rows:
        value = row.get(value_key, 0)
        values.append(float(value) if hasattr(value, "quantize") else value)
    return {
        "type": "doughnut",
        "labels": [row.get(label_key, "") for row in rows],
        "series": [{"label": "Total", "data": values}],
    }
