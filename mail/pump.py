"""Pompe de fond : vide la file SMTP automatiquement, sans cron ni bouton.

Un thread démon, démarré par ``mail.apps.MailConfig.ready``, passe toutes les
``MAIL_PUMP_SECONDS`` et envoie un lot borné par le lissage
(``MAIL_RATE_PER_MINUTE``). La réservation « sending » de ``_try_send`` rend la
pompe, le cron, le bouton manuel et l'envoi immédiat mutuellement exclusifs.
Désactivable : ``mail.pump = false`` dans instance.json ou ``MDL_MAIL_PUMP=0``
(le cron reste alors le vidage automatique).
"""
from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)

_demarree = False


def demarrer() -> None:
    global _demarree
    if _demarree:
        return
    _demarree = True
    threading.Thread(target=_boucle, name="mdl-mail-pump", daemon=True).start()
    logger.info("pompe SMTP démarrée")


def _boucle() -> None:
    import time

    from django.conf import settings
    from django.db import close_old_connections

    from mail.services import drain_outbox

    while True:
        intervalle = max(5, int(getattr(settings, "MAIL_PUMP_SECONDS", 15)))
        time.sleep(intervalle)
        try:
            if getattr(settings, "MAIL_ENABLED", False):
                cadence = int(getattr(settings, "MAIL_RATE_PER_MINUTE", 15))
                drain_outbox(limit=max(1, cadence * intervalle // 60))
        except Exception:  # noqa: BLE001 - la pompe ne doit jamais mourir
            logger.debug("pompe SMTP : passe en échec", exc_info=True)
        finally:
            close_old_connections()
