"""Jetons Ed25519 du canal d'intervention (hub éditeur / mode hors ligne)."""
from __future__ import annotations

import base64
import binascii
import hashlib
import time

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

TOKEN_VERSION = "v1"
# Liste blanche d'actions : rien d'autre ne peut être appliqué.
ALLOWED_ACTIONS = ("reset_password", "disable_2fa", "resend_invite", "health", "block", "unblock")


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64d(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def generate_keypair() -> tuple[str, str]:
    """Retourne (clé publique PEM, clé privée PEM)."""
    private = Ed25519PrivateKey.generate()
    priv_pem = private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")
    pub_pem = (
        private.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode("ascii")
    )
    return pub_pem, priv_pem


def load_public(pem: str) -> Ed25519PublicKey | None:
    try:
        key = serialization.load_pem_public_key(pem.encode("ascii"))
    except (ValueError, TypeError, binascii.Error):
        return None
    return key if isinstance(key, Ed25519PublicKey) else None


def load_private(pem: str) -> Ed25519PrivateKey | None:
    try:
        key = serialization.load_pem_private_key(pem.encode("ascii"), password=None)
    except (ValueError, TypeError, binascii.Error):
        return None
    return key if isinstance(key, Ed25519PrivateKey) else None


def sign(private_pem: str, install_id: str, action: str, target: str, code: str,
         ttl_minutes: int, reason: str = "") -> str:
    """Fabrique un jeton signé ``v1|install|action|target|code|exp|reason.signature``."""
    if action not in ALLOWED_ACTIONS:
        raise ValueError("action hors liste blanche : %s" % action)
    key = load_private(private_pem)
    if key is None:
        raise ValueError("clé privée invalide")
    exp = int(time.time()) + max(1, int(ttl_minutes)) * 60
    payload = "%s|%s|%s|%s|%s|%d|%s" % (TOKEN_VERSION, install_id, action, target, code, exp, reason)
    signature = _b64e(key.sign(payload.encode("utf-8")))
    return "%s.%s" % (_b64e(payload.encode("utf-8")), signature)


def verify(token: str, public_pem: str, install_id: str) -> dict:
    """Vérifie signature, expiration, ID d'install et liste blanche d'actions."""
    try:
        raw_payload, signature = token.strip().split(".", 1)
        payload = _b64d(raw_payload).decode("utf-8")
    except (ValueError, binascii.Error, UnicodeDecodeError):
        return {"ok": False, "error": "jeton illisible"}
    parts = payload.split("|")
    if len(parts) != 7:
        return {"ok": False, "error": "jeton mal formé"}
    version, tok_install, action, target, code, exp, reason = parts
    if version != TOKEN_VERSION:
        return {"ok": False, "error": "version de jeton inconnue"}
    key = load_public(public_pem)
    if key is None:
        return {"ok": False, "error": "clé publique absente ou invalide"}
    try:
        key.verify(_b64d(signature), payload.encode("utf-8"))
    except InvalidSignature:
        return {"ok": False, "error": "signature invalide"}
    if int(exp) < int(time.time()):
        return {"ok": False, "error": "jeton expiré"}
    if tok_install != install_id:
        return {"ok": False, "error": "ce jeton ne concerne pas cette installation"}
    if action not in ALLOWED_ACTIONS:
        return {"ok": False, "error": "action non autorisée : %s" % action}
    return {
        "ok": True,
        "action": action,
        "target": target,
        "code": code,
        "reason": reason,
        "expires_at": int(exp),
    }


def sha256(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()
