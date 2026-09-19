"""Stockage des fichiers : disque du serveur (défaut) ou objet S3 tiers.

Le choix est un réglage (Réglages → Stockage, ou à l'installation) :

* « Sur le serveur » : comportement historique, ``MEDIA_ROOT``.
* « Chez un fournisseur tiers » : n'importe quel stockage compatible S3
  (Backblaze B2 — 10 Go gratuits sans carte bancaire, Cloudflare R2,
  Supabase, MinIO, Scaleway…). Le client est minimal (PUT/GET/HEAD/DELETE
  signés SigV4) pour rester sans dépendance supplémentaire.

``ConfiguredStorage`` est le stockage par défaut de Django : il délègue au
disque local ou au S3 selon le réglage courant. Les fichiers déjà présents
sur le disque continuent d'être servis même après le passage au S3.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import urllib.error
import urllib.request
from datetime import UTC, datetime
from urllib.parse import quote

from django.conf import settings
from django.core.files.base import ContentFile, File
from django.core.files.storage import FileSystemStorage, Storage
from django.utils.deconstruct import deconstructible

SERVICE = "s3"

# Endpoint Backblaze B2 : s3.<région>.backblazeb2.com — la région y est lisible.
_B2_REGION = re.compile(r"^s3\.([a-z]{2}-[a-z]+-\d{3})\.backblazeb2\.com$", re.IGNORECASE)


def derive_region(endpoint: str) -> str:
    """Région lisible dans l'endpoint (B2) ; vide sinon (R2 signe avec « auto »)."""
    host = (endpoint or "").split("://")[-1].split("/")[0]
    match = _B2_REGION.match(host)
    return match.group(1) if match else ""


def effective_region(cfg: dict) -> str:
    """Région signée : celle saisie, sinon celle devinée depuis l'endpoint, sinon « auto ».

    B2 refuse une signature dont la région n'est pas celle du bucket (HTTP 403) ;
    R2, à l'inverse, exige « auto ».
    """
    region = (cfg.get("region") or "").strip()
    if region and region != "auto":
        return region
    return derive_region(cfg.get("endpoint") or "") or "auto"


def stockage_cfg() -> dict:
    """Réglage courant du stockage (section « stockage »), sans planter sans base."""
    from core.models import Setting

    try:
        return Setting.data().get("stockage", {}) or {}
    except Exception:  # base absente/pas migrée (manage.py migrate, tests précoces)
        return {}


def s3_pret(cfg: dict) -> bool:
    return cfg.get("provider") == "s3" and all(
        cfg.get(k) for k in ("endpoint", "bucket", "access_key", "secret_key"))


# --------------------------------------------------------------------------- #
# Signature SigV4 + client HTTP minimal
# --------------------------------------------------------------------------- #
def _hmac(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def signed_headers(method: str, host: str, path: str, access_key: str, secret_key: str,
                   region: str, payload: bytes = b"", query: str = "", now=None,
                   service: str = SERVICE, extra_headers: dict | None = None) -> dict:
    """En-têtes signés AWS SigV4 pour une requête S3 (path-style)."""
    now = now or datetime.now(UTC)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")
    payload_hash = hashlib.sha256(payload).hexdigest()
    headers = {
        "host": host,
        "x-amz-content-sha256": payload_hash,
        "x-amz-date": amz_date,
    }
    headers.update(extra_headers or {})
    canonical_headers = "".join("%s:%s\n" % (k, headers[k]) for k in sorted(headers))
    signed = ";".join(sorted(headers))
    canonical_request = "\n".join([method, quote(path, safe="/~"), query,
                                   canonical_headers, signed, payload_hash])
    scope = "%s/%s/%s/aws4_request" % (date_stamp, region or "auto", service)
    string_to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope,
                                hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()])
    key = _hmac(("AWS4" + secret_key).encode("utf-8"), date_stamp)
    key = _hmac(key, region or "auto")
    key = _hmac(key, service)
    key = _hmac(key, "aws4_request")
    signature = hmac.new(key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    headers["Authorization"] = ("AWS4-HMAC-SHA256 Credential=%s/%s, SignedHeaders=%s, Signature=%s"
                                % (access_key, scope, signed, signature))
    return headers


class S3Error(RuntimeError):
    pass


def s3_request(cfg: dict, method: str, name: str, payload: bytes = b"") -> bytes:
    """Exécute une requête S3 path-style (/{bucket}/{name}) et renvoie le corps."""
    endpoint = (cfg.get("endpoint") or "").rstrip("/")
    if "://" not in endpoint:
        endpoint = "https://" + endpoint
    scheme, _, hostport = endpoint.partition("://")
    host = hostport.split("/")[0]
    region = effective_region(cfg)
    bucket = cfg["bucket"]
    path = "/%s/%s" % (bucket, name) if name else "/%s" % bucket
    url = "%s://%s%s" % (scheme, host, quote(path, safe="/~"))
    headers = signed_headers(method, host, path, cfg["access_key"], cfg["secret_key"],
                             region, payload=payload)
    headers.pop("host", None)  # urllib le pose lui-même
    request = urllib.request.Request(url, data=payload if method in ("PUT", "POST") else None,
                                     headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # nosec B310 — https forcé
            return response.read()
    except urllib.error.HTTPError as exc:
        corps = ""
        try:
            corps = exc.read(600).decode("utf-8", "replace").strip()
        except Exception:
            pass
        code = ""
        for balise in ("Code", "Message"):
            debut = corps.find("<%s>" % balise)
            if debut != -1:
                fin = corps.find("</%s>" % balise)
                code += " %s=%s" % (balise, corps[debut + len(balise) + 2:fin])
        raise S3Error("S3 %s %s : HTTP %s %s%s" % (method, name, exc.code, exc.reason, code)) from exc
    except urllib.error.URLError as exc:
        raise S3Error("S3 injoignable (%s) : %s" % (host, exc.reason)) from exc


def list_objects(cfg: dict, prefix: str = "") -> list[str]:
    """Liste les clés du bucket (LIST v2, pages de 1000)."""
    import xml.etree.ElementTree as ET

    endpoint = (cfg.get("endpoint") or "").rstrip("/")
    if "://" not in endpoint:
        endpoint = "https://" + endpoint
    host = endpoint.split("://")[1].split("/")[0]
    region = effective_region(cfg)
    bucket = cfg["bucket"]
    cles = []
    token = ""
    while True:
        params = [("list-type", "2"), ("max-keys", "1000")]
        if prefix:
            params.append(("prefix", prefix))
        if token:
            params.append(("continuation-token", token))
        query = "&".join("%s=%s" % (k, quote(v, safe="~")) for k, v in sorted(params))
        path = "/%s" % bucket
        headers = signed_headers("GET", host, path, cfg["access_key"], cfg["secret_key"],
                                 region, query=query)
        headers.pop("host", None)
        url = "%s://%s%s?%s" % (endpoint.split("://")[0], host, quote(path, safe="/~"), query)
        request = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(request, timeout=30) as response:  # nosec B310 — https forcé
            corps = response.read()
        racine = ET.fromstring(corps)
        namespace = racine.tag.split("}")[0] + "}" if "}" in racine.tag else ""
        for cle in racine.findall("%sContents/%sKey" % (namespace, namespace)):
            cles.append(cle.text or "")
        suivant = racine.find("%sNextContinuationToken" % namespace)
        if suivant is None or not suivant.text:
            break
        token = suivant.text
    return cles


def purge_all(cfg: dict) -> int:
    """Supprime tous les objets du bucket (réinitialisation du site)."""
    cles = list_objects(cfg)
    for cle in cles:
        s3_request(cfg, "DELETE", cle)
    return len(cles)


# --------------------------------------------------------------------------- #
# Stockages
# --------------------------------------------------------------------------- #
@deconstructible
class S3Storage(Storage):
    """Stockage objet compatible S3 (Backblaze B2, R2, Supabase, MinIO…)."""

    def __init__(self, cfg: dict):
        self.cfg = dict(cfg)

    def _save(self, name, content):
        data = content.read()
        s3_request(self.cfg, "PUT", name, payload=data)
        return name

    def _open(self, name, mode="rb"):
        return File(__import__("io").BytesIO(s3_request(self.cfg, "GET", name)), name=name)

    def delete(self, name):
        try:
            s3_request(self.cfg, "DELETE", name)
        except S3Error as exc:
            if "404" not in str(exc):
                raise

    def exists(self, name):
        try:
            s3_request(self.cfg, "HEAD", name)
            return True
        except S3Error as exc:
            if "404" in str(exc):
                return False
            raise

    def size(self, name):
        raise NotImplementedError  # la taille est enregistrée en base à l'upload

    def url(self, name):
        return "/fichiers/" + name


@deconstructible
class ConfiguredStorage(Storage):
    """Stockage par défaut : disque local ou S3 selon le réglage « stockage ».

    Lecture : si l'objet est absent du S3, repli sur le disque local (les
    fichiers téléversés avant le passage au S3 restent servis).
    """

    def __init__(self):
        self._local = None
        self._s3 = None
        self._s3_key = None

    @property
    def local(self) -> FileSystemStorage:
        if self._local is None:
            self._local = FileSystemStorage(location=str(settings.MEDIA_ROOT), base_url="/fichiers/")
        return self._local

    def _backend(self):
        cfg = stockage_cfg()
        if s3_pret(cfg):
            key = tuple(sorted((k, cfg.get(k)) for k in
                               ("endpoint", "region", "bucket", "access_key", "secret_key")))
            if self._s3 is None or self._s3_key != key:
                self._s3 = S3Storage(cfg)
                self._s3_key = key
            return self._s3
        return self.local

    # -- écriture : toujours vers le fournisseur courant ------------------- #
    def _save(self, name, content):
        backend = self._backend()
        if backend is self.local:
            return self.local._save(name, content)
        data = content.read()
        backend._save(name, ContentFile(data))
        # copie locale de sécurité impossible sans doublon de quota : non
        return name

    def generate_filename(self, filename):
        return self.local.generate_filename(filename)

    # -- lecture : S3 puis repli local -------------------------------------- #
    def _open(self, name, mode="rb"):
        backend = self._backend()
        if backend is not self.local:
            try:
                if backend.exists(name):
                    return backend._open(name, mode)
            except S3Error:
                pass
        return self.local._open(name, mode)

    def exists(self, name):
        backend = self._backend()
        if backend is not self.local:
            try:
                if backend.exists(name):
                    return True
            except S3Error:
                return False
        return self.local.exists(name)

    def delete(self, name):
        backend = self._backend()
        if backend is not self.local:
            try:
                backend.delete(name)
            except S3Error:
                pass
        if self.local.exists(name):
            self.local.delete(name)

    def size(self, name):
        backend = self._backend()
        if backend is not self.local and not self.local.exists(name):
            raise NotImplementedError
        return self.local.size(name)

    def url(self, name):
        return "/fichiers/" + name

    def listdir(self, path):
        return self.local.listdir(path)

    def path(self, name):
        return self.local.path(name)
