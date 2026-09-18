

def test_vidage_complet_du_journal(db):
    """L'administrateur peut vider le journal ; la purge par lots contourne
    le garde-fou d'immuabilité, qui ne bloque que la suppression ligne à ligne."""
    from audit import services as audit
    from audit.models import AuditEntry

    for i in range(7):
        audit.log(None, "auth.login", "accounts", None, "ligne %d" % i)
    assert AuditEntry.objects.count() == 7

    assert audit.empty_log(dry_run=True) == 7
    assert AuditEntry.objects.count() == 7, "dry_run ne doit rien supprimer"

    assert audit.empty_log() == 7
    assert AuditEntry.objects.count() == 0


def test_bouton_vider_depuis_l_interface(admin_client):
    from django.urls import reverse

    from audit import services as audit
    from audit.models import AuditEntry

    for i in range(5):
        audit.log(None, "auth.login", "accounts", None, "ligne %d" % i)

    page = admin_client.get(reverse("audit:audit_list"))
    assert "Vider le journal" in page.content.decode()

    response = admin_client.post(reverse("audit:audit_clear"), follow=True)
    assert response.status_code == 200
    # Le journal repart vide, à l'exception de la ligne qui trace le vidage.
    assert AuditEntry.objects.count() == 1
    assert AuditEntry.objects.get().action == "settings.audit_cleared"


def test_vidage_refuse_au_non_administrateur(member_client):
    from django.urls import reverse

    assert member_client.post(reverse("audit:audit_clear")).status_code == 403


def test_vidage_refuse_en_get(admin_client):
    from django.urls import reverse

    assert admin_client.get(reverse("audit:audit_clear")).status_code == 403
