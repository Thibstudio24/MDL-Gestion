"""A2F TOTP (RFC 6238, SHA-1, 6 chiffres, 30 s, fenêtre ±1 pas, anti-rejeu)."""
from __future__ import annotations

import hashlib
import re
import secrets

import pyotp
import segno
from django.utils import timezone

from accounts.models import RecoveryCode

PERIOD = 30
DIGITS = 6
ISSUER = "MDL Gestion"


def generate_secret() -> str:
    return pyotp.random_base32(length=32)


def provisioning_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret, interval=PERIOD, digits=DIGITS).provisioning_uri(name=email, issuer_name=ISSUER)


def qr_svg(uri: str) -> str:
    """QR en SVG inline (segno, sans Pillow), redimensionnable sans rognage.

    segno émet un SVG sans viewBox : redimensionné en CSS, le dessin ne suit pas
    et le code est coupé en bas à droite. On injecte donc le viewBox (espace du
    dessin = width × height) pour que le QR reste entier à toute taille.
    """
    svg = segno.make(uri, error="m").svg_inline(scale=6)
    if "viewBox" not in svg:
        dimensions = re.search(r'width="(\d+)" height="(\d+)"', svg)
        if dimensions:
            svg = svg.replace(dimensions.group(0),
                              '%s viewBox="0 0 %s %s"' % (dimensions.group(0),
                                                          dimensions.group(1),
                                                          dimensions.group(2)), 1)
    return svg


def verify(secret: str, code: str, user=None) -> bool:
    """Vérifie le code avec une fenêtre de ±1 pas et bloque le rejeu du même pas."""
    code = (code or "").strip()
    if not secret or len(code) != DIGITS or not code.isdigit():
        return False
    totp = pyotp.TOTP(secret, interval=PERIOD, digits=DIGITS)
    step = int(timezone.now().timestamp() // PERIOD)
    for offset in (0, -1, 1):
        candidate_step = step + offset
        if totp.verify(code, for_time=candidate_step * PERIOD, valid_window=0):
            from django.core.cache import cache

            key = "totp:%s:%s" % (getattr(user, "pk", "?"), candidate_step)
            if cache.get(key):
                return False  # anti-rejeu : ce pas a déjà été utilisé
            cache.set(key, 1, PERIOD * 3)
            return True
    return False


def generate_recovery_codes(user, count: int = 10) -> list[str]:
    """10 codes de récupération à usage unique (SHA-256 en base, affichés une seule fois)."""
    RecoveryCode.objects.filter(user=user, used_at__isnull=True).delete()
    codes = []
    for _ in range(count):
        raw = "%s-%s" % (secrets.token_hex(3).upper(), secrets.token_hex(3).upper())
        codes.append(raw)
        RecoveryCode.objects.create(user=user, hash=hashlib.sha256(raw.encode()).hexdigest())
    return codes


def use_recovery_code(user, code: str) -> bool:
    code = (code or "").strip().upper()
    if not code:
        return False
    digest = hashlib.sha256(code.encode()).hexdigest()
    record = RecoveryCode.objects.filter(user=user, hash=digest, used_at__isnull=True).first()
    if record is None:
        return False
    record.used_at = timezone.now()
    record.save(update_fields=["used_at"])
    try:
        from audit.services import log

        log(user, "auth.2fa_recovery_used", "accounts", user,
            "Code de récupération A2F utilisé (%d restants)" % recovery_codes_left(user),
            level="warn")
    except Exception:
        pass
    return True


def recovery_codes_left(user) -> int:
    return RecoveryCode.objects.filter(user=user, used_at__isnull=True).count()
