

def test_a2f_demandee_des_la_premiere_connexion(client, member):
    """Un rôle qui impose l'A2F doit la demander dès la création du compte :
    sans application par le middleware, force_2fa ne servait à rien."""
    from django.urls import reverse

    member.role.force_2fa = True
    member.role.save(update_fields=["force_2fa"])
    member.totp_enabled = False
    member.totp_confirmed_at = None
    member.save(update_fields=["totp_enabled", "totp_confirmed_at"])

    client.force_login(member)
    response = client.get("/")
    assert response.status_code == 302
    assert response.headers["Location"] == reverse("auth:twofa_setup")


def test_a2f_reportable_pendant_le_delai_puis_obligatoire(client, member):
    from datetime import timedelta

    from django.urls import reverse
    from django.utils import timezone

    member.role.force_2fa = True
    member.role.force_2fa_deadline_days = 14
    member.role.save(update_fields=["force_2fa", "force_2fa_deadline_days"])
    member.totp_enabled = False
    member.totp_confirmed_at = None
    member.save(update_fields=["totp_enabled", "totp_confirmed_at"])

    client.force_login(member)
    client.post(reverse("auth:twofa_defer"), {"next": "/"}, follow=True)
    assert client.get("/").status_code == 200, "le report doit laisser naviguer pendant le délai"

    # Délai dépassé : le report ne suffit plus.
    member.created_at = timezone.now() - timedelta(days=30)
    member.save(update_fields=["created_at"])
    member.refresh_from_db()
    assert member.two_factor_overdue is True

    response = client.get("/")
    assert response.status_code == 302
    assert response.headers["Location"] == reverse("auth:twofa_setup")


def test_aucun_blocage_si_le_role_nimpose_pas_la2f(client, member):
    member.role.force_2fa = False
    member.role.save(update_fields=["force_2fa"])

    client.force_login(member)
    assert client.get("/").status_code == 200
