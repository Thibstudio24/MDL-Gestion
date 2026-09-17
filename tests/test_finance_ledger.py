

def test_destinataires_du_bilan_derivent_du_droit_tresorerie(year, admin):
    """Les destinataires ne se choisissent pas : ils découlent du droit de
    consulter la trésorerie, le même droit qui ouvre la catégorie « Bilans »."""
    from accounts.models import Role, User
    from accounts.services import _apply_levels
    from documents.models import Category
    from documents.services import ensure_default_categories
    from finance.services import finance_viewers, generate_balance
    from notifications.models import Notification

    ensure_default_categories()
    assert Category.objects.get(name="Bilans").module_gate == "finance"

    tresorier_role = Role.objects.create(name="Trésorier", slug="tresorier")
    _apply_levels(tresorier_role, {"finance": 1}, [])
    simple_role = Role.objects.create(name="Simple", slug="simple")
    _apply_levels(simple_role, {"finance": 0}, [])

    User.objects.create_user(email="treso@mdl.test", password="MotDePasse!2026",
                             role=tresorier_role)
    User.objects.create_user(email="simple@mdl.test", password="MotDePasse!2026",
                             role=simple_role)

    viewers = {user.email for user in finance_viewers()}
    assert "treso@mdl.test" in viewers
    assert "simple@mdl.test" not in viewers

    run = generate_balance(year, actor=admin)
    assert run.status == "ok"

    notified = {entry.user.email
                for entry in Notification.objects.filter(kind="bilan_generated")}
    assert "treso@mdl.test" in notified
    assert "simple@mdl.test" not in notified, "un membre sans droit trésorerie a été notifié"


def test_le_formulaire_bilan_ne_propose_plus_de_destinataires(admin_client):
    from django.urls import reverse

    from core.models import Setting

    page = admin_client.get(reverse("settings:settings_bilan"))
    assert 'name="destinataires"' not in page.content.decode()

    admin_client.post(reverse("settings:settings_bilan"), {
        "auto": "on", "mode": "dernier", "jour": "1", "heure": "06:30",
        "categorie": "Bilans",
    }, follow=True)
    # Valeur imposée par la vue, quoi qu'il arrive.
    assert Setting.data()["bilan"]["destinataires"] == "module"
