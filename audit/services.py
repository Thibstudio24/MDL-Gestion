"""Écriture du journal d'audit et purge informative après N années."""
from __future__ import annotations

import json
from datetime import timedelta

from django.utils import timezone

from audit.models import AuditEntry


def _label(actor) -> str:
    if actor is None:
        return "système"
    return getattr(actor, "email", str(actor))


def _changes(previous, current) -> dict:
    out = {}
    for key, value in (current or {}).items():
        old = (previous or {}).get(key)
        if old != value:
            out[key] = {"avant": _serializable(old), "apres": _serializable(value)}
    return out


def _serializable(value):
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def log(actor, action: str, module: str, obj=None, message: str = "", *,
        previous: dict | None = None, current: dict | None = None,
        level: str = "info", request=None, origin: str | None = None) -> AuditEntry:
    """Écrit une ligne d'audit. Ne lève jamais d'exception (le journal ne bloque pas le métier)."""
    try:
        entry = AuditEntry(
            actor=actor if getattr(actor, "pk", None) else None,
            actor_label=_label(actor),
            action=action,
            module=module,
            model_name=type(obj).__name__ if obj is not None else "",
            object_id=str(getattr(obj, "pk", "") or "")[:64],
            object_repr=(str(obj)[:240] if obj is not None else ""),
            message=(message or "")[:400],
            changes=_changes(previous, current) if (previous is not None or current is not None) else {},
            level=level,
            ip=getattr(request, "client_ip", None) if request is not None else None,
            user_agent=(getattr(request, "user_agent", "") or "")[:240] if request is not None else "",
            origin=origin or getattr(request, "origin", "web") or "web",
        )
        AuditEntry.objects.bulk_create([entry])
        return entry
    except Exception:  # pragma: no cover - le journal ne doit jamais casser une action
        return AuditEntry(action=action, actor_label=_label(actor), message=message[:400], level=level)


def changes_for(obj, fields) -> dict:
    """Instantané des champs pour comparaison avant/après."""
    out = {}
    for field in fields:
        out[field] = getattr(obj, field, None)
    return out


def purge_audit(years: int, dry_run: bool = False) -> int:
    limit = timezone.now() - timedelta(days=365 * max(1, int(years or 5)))
    queryset = AuditEntry.objects.filter(at__lt=limit)
    count = queryset.count()
    if not dry_run and count:
        deleted = 0
        for batch_start in range(0, count, 500):
            ids = list(queryset.values_list("pk", flat=True)[batch_start:batch_start + 500])
            if not ids:
                break
            deleted += AuditEntry.objects.filter(pk__in=ids).delete()[0]
        return deleted
    return count


def export_rows(queryset):
    for entry in queryset.iterator(chunk_size=500):
        yield [
            entry.at.strftime("%d/%m/%Y %H:%M:%S"),
            entry.actor_label,
            entry.action,
            entry.module,
            entry.object_repr,
            entry.message,
            entry.level,
            entry.origin,
            entry.ip or "",
            json.dumps(entry.changes, ensure_ascii=False, default=str) if entry.changes else "",
        ]
