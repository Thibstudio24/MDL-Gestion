"""Export PDF du grand livre (reportlab, aucune dépendance système).

Le PDF A4 paysage reprend exactement les colonnes du grand livre à l'écran et de
l'export Excel : date, libellé, compte, catégorie, mode, tiers, puis dépenses et
recettes séparées. Les montants sont rendus au format français (1 250,50 €) et les
dates en ``d/m/Y`` — la même mise en forme que partout ailleurs dans l'application.
"""
from __future__ import annotations

from typing import Any

from django.http import HttpResponse

from core.export import pdf_landscape_response
from core.templatetags.ui import date_fr, money

#: Largeurs de colonnes en points (A4 paysage, marges 15 mm ≈ 252 pt utiles).
COLUMN_WIDTHS = [46, 132, 58, 62, 40, 66, 52, 52]

HEADERS = ["Date", "Libellé", "Compte", "Catégorie", "Mode", "Tiers", "Dépense", "Recette"]


def ledger_rows(entries) -> list[list[Any]]:
    """Une ligne par écriture ; les montants restent des ``Decimal`` (mis en forme plus bas)."""
    rows = []
    for entry in entries:
        rows.append([
            date_fr(entry.day),
            entry.title,
            entry.account.name,
            entry.category.label if entry.category_id else "",
            entry.get_mode_display() or "",
            entry.third_party or "",
            entry.amount if entry.kind == "D" else "",
            entry.amount if entry.kind == "R" else "",
        ])
    return rows


def ledger_pdf(year, entries, totals: dict[str, Any], filters: str = "") -> HttpResponse:
    """Grand livre complet en PDF, avec ligne de totaux en bas de tableau."""
    count = len(entries) if isinstance(entries, list) else entries.count()
    subtitle = "%s écriture(s) · du %s au %s" % (
        count,
        date_fr(year.start_date),
        date_fr(year.end_date),
    )
    if filters:
        subtitle += " · filtres : %s" % filters
    totals_row = [
        "Totaux",
        "%s · dépenses %s · recettes %s"
        % (year.label, money(totals.get("expenses")), money(totals.get("incomes"))),
        "", "", "", "",
        totals.get("expenses"),
        totals.get("incomes"),
    ]
    return pdf_landscape_response(
        filename="grand-livre-%s.pdf" % year.label,
        title="Grand livre %s" % year.label,
        headers=HEADERS,
        rows=ledger_rows(entries),
        subtitle=subtitle,
        totals=totals_row,
        column_widths=COLUMN_WIDTHS,
        footer_note="Solde au terme de la période : %s" % money(totals.get("balance")),
    )
