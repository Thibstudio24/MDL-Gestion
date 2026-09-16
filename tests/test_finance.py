"""Trésorerie : soldes, transferts, coffre, clôture dure, imports, bilan."""
from __future__ import annotations

import io
from datetime import date
from decimal import Decimal

import pytest

from finance import services
from finance.models import Account, CashCount, Entry, ImportBatch, MonthLock
from finance.services import FinanceError


@pytest.fixture
def accounts(db):
    services.ensure_accounts()
    services.ensure_default_categories()
    services.ensure_gap_category()
    return Account.objects.get(name="Compte bancaire"), Account.objects.get(name="Coffre-fort")


@pytest.fixture
def bank(accounts):
    return accounts[0]


@pytest.fixture
def safe(accounts):
    return accounts[1]


class TestSoldes:
    def test_solde_initial_nul(self, year, bank):
        assert services.balance_for_account(year, bank)["total"] == Decimal("0.00")

    def test_recette_puis_depense(self, year, bank, admin):
        services.create_entry(admin, year, day=year.start_date, title="Subvention",
                              amount=Decimal("1200.00"), kind="R", account=bank)
        services.create_entry(admin, year, day=year.start_date, title="Fournitures",
                              amount=Decimal("84.50"), kind="D", account=bank)
        assert services.balance_for_account(year, bank)["total"] == Decimal("1115.50")

    def test_transfert_sort_du_compte_et_entre_au_coffre(self, year, bank, safe, admin):
        services.create_entry(admin, year, day=year.start_date, title="Retrait",
                              amount=Decimal("100.00"), kind="T", account=bank, to_account=safe)
        assert services.balance_for_account(year, bank)["total"] == Decimal("-100.00")
        assert services.safe_balance(year) == Decimal("100.00")

    def test_transfert_vers_le_meme_compte_refuse(self, year, bank, admin):
        with pytest.raises(FinanceError):
            services.create_entry(admin, year, day=year.start_date, title="Boucle",
                                  amount=Decimal("10"), kind="T", account=bank, to_account=bank)

    def test_montant_negatif_refuse(self, year, bank, admin):
        with pytest.raises(FinanceError):
            services.create_entry(admin, year, day=year.start_date, title="Négatif",
                                  amount=Decimal("-5"), kind="D", account=bank)

    def test_solde_douverture_pris_en_compte(self, year, bank):
        from finance.models import AccountOpening

        AccountOpening.objects.create(year=year, account=bank, amount=Decimal("500.00"))
        assert services.balance_for_account(year, bank)["total"] == Decimal("500.00")


class TestAgregats:
    def test_flux_de_lannee(self, year, bank, admin):
        services.create_entry(admin, year, day=year.start_date, title="Recette",
                              amount=Decimal("200"), kind="R", account=bank)
        services.create_entry(admin, year, day=year.start_date, title="Dépense",
                              amount=Decimal("50"), kind="D", account=bank)
        flows = services.year_flows(year)
        assert flows["incomes"] == Decimal("200")
        assert flows["expenses"] == Decimal("50")
        assert flows["balance"] == Decimal("150")

    def test_histogramme_mensuel(self, year, bank, admin):
        services.create_entry(admin, year, day=year.start_date, title="Recette",
                              amount=Decimal("100"), kind="R", account=bank)
        histogram = services.year_histogram(year)
        assert len(histogram) == len(year.months())
        assert histogram[0]["income_value"] == 100.0

    def test_repartition_par_categorie(self, year, bank, admin):
        from finance.models import Category

        category = Category.objects.filter(kind="D").first()
        services.create_entry(admin, year, day=year.start_date, title="Achat",
                              amount=Decimal("30"), kind="D", account=bank, category=category)
        rows = services.category_breakdown(year, "D")
        assert rows and rows[0]["total"] == Decimal("30")


class TestCloture:
    def test_verrou_dur_bloque_la_saisie(self, year, bank, admin):
        services.generate_balance(year, up_to=year.start_date, actor=admin)
        services.lock_month(year, year.start_date.month, year.start_date.year, admin)
        with pytest.raises(FinanceError):
            services.create_entry(admin, year, day=year.start_date, title="Trop tard",
                                  amount=Decimal("10"), kind="D", account=bank)

    def test_verrou_dur_bloque_la_suppression(self, year, bank, admin):
        entry = services.create_entry(admin, year, day=year.start_date, title="À bloquer",
                                      amount=Decimal("10"), kind="D", account=bank)[0]
        services.generate_balance(year, up_to=year.start_date, actor=admin)
        services.lock_month(year, year.start_date.month, year.start_date.year, admin)
        with pytest.raises(FinanceError):
            services.delete_entry(admin, entry, "tentative")

    def test_reouverture_sans_motif_refusee(self, year, admin):
        services.generate_balance(year, up_to=year.start_date, actor=admin)
        services.lock_month(year, year.start_date.month, year.start_date.year, admin)
        with pytest.raises(FinanceError):
            services.unlock_month(year, year.start_date.month, year.start_date.year, admin, "")

    def test_reouverture_motivee_libere_le_mois(self, year, bank, admin):
        services.generate_balance(year, up_to=year.start_date, actor=admin)
        services.lock_month(year, year.start_date.month, year.start_date.year, admin)
        services.unlock_month(year, year.start_date.month, year.start_date.year, admin, "erreur de saisie")
        assert MonthLock.objects.filter(year=year).count() == 0
        services.create_entry(admin, year, day=year.start_date, title="De nouveau possible",
                              amount=Decimal("10"), kind="D", account=bank)

    def test_cloture_sans_bilan_refusee(self, year, admin):
        with pytest.raises(FinanceError):
            services.lock_month(year, 6, year.start_date.year + 1, admin)


class TestSuppression:
    def test_motif_obligatoire(self, year, bank, admin):
        entry = services.create_entry(admin, year, day=year.start_date, title="Erreur",
                                      amount=Decimal("10"), kind="D", account=bank)[0]
        with pytest.raises(FinanceError):
            services.delete_entry(admin, entry, "")

    def test_suppression_motivee_tracee(self, year, bank, admin):
        from audit.models import AuditEntry

        entry = services.create_entry(admin, year, day=year.start_date, title="Doublon",
                                      amount=Decimal("10"), kind="D", account=bank)[0]
        services.delete_entry(admin, entry, "saisie en double")
        assert Entry.objects.filter(pk=entry.pk).exists() is False
        assert AuditEntry.objects.filter(action="finance.entry_deleted").exists()


class TestCoffre:
    def test_ecart_juste_cree_une_regularisation(self, year, safe, admin):
        services.cash_count(admin, year, day=year.start_date, account=safe,
                            counted=Decimal("10.00"), reason="pièce perdue")
        count = CashCount.objects.get(year=year)
        assert count.delta == Decimal("10.00")
        assert count.adjustment is not None
        assert count.adjustment.kind == "R"
        assert count.adjustment.category.label == "Écart de caisse"

    def test_ecart_negatif_cree_une_charge(self, year, safe, admin):
        from finance.models import AccountOpening

        AccountOpening.objects.create(year=year, account=safe, amount=Decimal("100.00"))
        services.cash_count(admin, year, day=year.start_date, account=safe,
                            counted=Decimal("90.00"), reason="manquant")
        count = CashCount.objects.get(year=year)
        assert count.adjustment.kind == "D"
        assert services.safe_balance(year) == Decimal("90.00")

    def test_ecart_sans_motif_refuse(self, year, safe, admin):
        with pytest.raises(FinanceError):
            services.cash_count(admin, year, day=year.start_date, account=safe,
                                counted=Decimal("10.00"), reason="")


class TestImport:
    def test_lecture_csv(self, db):
        rows, fmt = services.read_import(io.BytesIO("date;libellé;montant\n12/10/2026;Cotisation;-5.00\n"
                                                    .encode()))
        assert fmt == "csv" and len(rows) == 1

    def test_lecture_ofx(self, db):
        ofx = ("<OFX><BANKTRANLIST><STMTTRN><TRNTYPE>DEBIT><DTPOSTED>20261012"
               "<TRNAMT>-12.50<NAME>Papeterie</STMTTRN></BANKTRANLIST></OFX>")
        rows, fmt = services.read_import(io.BytesIO(ofx.encode("utf-8")))
        assert fmt == "ofx" and rows[0]["amount"] == "-12.50"

    def test_lecture_qif(self, db):
        qif = "!Type:Bank\nD12/10/2026\nT-5,00\nPCotisation\n^\n"
        rows, fmt = services.read_import(io.BytesIO(qif.encode("utf-8")))
        assert fmt == "qif" and rows[0]["amount"] == "-5,00"

    def test_sens_devine_selon_le_signe(self, year, bank, db):
        rows, _fmt = services.read_import(io.BytesIO(
            "date;libellé;montant\n12/10/2026;Dépense;-5.00\n13/10/2026;Recette;42,50\n".encode()))
        prepared = services.prepare_import(rows, {"date": "date", "amount": "montant", "label": "libellé"},
                                           bank, year)
        assert [item["kind"] for item in prepared] == ["D", "R"]
        assert prepared[1]["amount"] == Decimal("42.50")

    def test_doublon_detecte(self, year, bank, admin, db):
        services.create_entry(admin, year, day=date(year.start_date.year, 10, 12), title="Cotisation",
                              amount=Decimal("5.00"), kind="D", account=bank)
        rows, _fmt = services.read_import(io.BytesIO(
            ("date;libellé;montant\n12/10/%d;Cotisation;-5.00\n" % year.start_date.year).encode("utf-8")))
        prepared = services.prepare_import(rows, {"date": "date", "amount": "montant", "label": "libellé"},
                                           bank, year)
        assert prepared[0]["duplicate"] is True

    def test_import_puis_annulation(self, year, bank, admin, db):
        rows, _fmt = services.read_import(io.BytesIO(
            "date;libellé;montant\n12/10/2026;Cotisation;-5.00\n".encode()))
        prepared = services.prepare_import(rows, {"date": "date", "amount": "montant", "label": "libellé"},
                                           bank, year)
        batch = ImportBatch.objects.create(file_name="test.csv", year=year, rows_total=1, created_by=admin)
        services.run_import(admin, batch, prepared, bank, year)
        assert batch.rows_created == 1
        assert Entry.objects.filter(import_batch=batch).count() == 1
        assert services.revert_import(admin, batch) == 1
        assert Entry.objects.filter(import_batch=batch).count() == 0


class TestBilan:
    def test_generation_du_classeur(self, year, bank, admin):
        services.create_entry(admin, year, day=year.start_date, title="Recette",
                              amount=Decimal("100"), kind="R", account=bank)
        run = services.generate_balance(year, up_to=year.start_date, actor=admin)
        assert run.status == "ok"
        assert run.workbook is not None
        assert run.months

    def test_le_bilan_est_classe_dans_les_documents(self, year, bank, admin):
        from documents.models import Category as DocCategory

        services.generate_balance(year, up_to=year.start_date, actor=admin)
        assert DocCategory.objects.filter(slug="bilans").exists()

    def test_echeance_du_dernier_jour_ouvre(self, year, db):
        from core.models import Setting

        Setting.update_section("bilan", {"mode": "dernier"})
        assert services.should_generate_today(year.end_date, year) is True

    def test_hors_echeance(self, year, db):
        from core.models import Setting

        Setting.update_section("bilan", {"mode": "jour", "jour": "1"})
        assert services.should_generate_today(year.start_date + __import__("datetime").timedelta(days=5),
                                              year) is False

    def test_export_excel_du_grand_livre(self, admin_client, year, bank, admin):
        services.create_entry(admin, year, day=year.start_date, title="Recette",
                              amount=Decimal("100"), kind="R", account=bank)
        response = admin_client.get("/tresorerie/export/?format=xlsx")
        assert response.status_code == 200
        assert response["Content-Disposition"].startswith("attachment")
