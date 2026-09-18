"""Export PDF du planning de la salle (reportlab, aucune dépendance système).

Deux pages A4 paysage :

1. **Grille des créneaux** — ce qu'on imprime et qu'on affiche sur la porte du
   foyer : jour, horaire, intitulé, gérants nécessaires, membres disponibles,
   membres « si besoin », état du créneau (couvert / à pourvoir).
2. **Synthèse par membre** — qui a répondu quoi, pour préparer les relances.

Mêmes couleurs et mêmes marges que les autres exports PDF de l'application ;
dates en ``d/m/Y`` et heures en ``H:M``, comme partout ailleurs.
"""
from __future__ import annotations

import io

from django.http import HttpResponse
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from core.export import brand_lines
from plannings import services

HEADER_BG = colors.HexColor("#33556E")
ZEBRA = colors.HexColor("#F4F6F8")
GRID = colors.HexColor("#D3DBE3")
MUTED = colors.HexColor("#5A6570")
GAP_BG = colors.HexColor("#FBE9E7")

#: Largeurs en points ; A4 paysage moins 30 mm de marges ≈ 792 - 85 = 707 pt.
GRID_WIDTHS = [62, 78, 150, 62, 175, 110, 70]
MEMBER_WIDTHS = [190, 100, 100, 100, 217]

GRID_HEADERS = ["Jour", "Horaire", "Intitulé", "Gérants requis", "Disponibles", "Si besoin", "État"]
MEMBER_HEADERS = ["Membre", "Disponibles", "Si besoin", "Indisponibles", "Créneaux concernés"]


def _table_style(row_count: int, highlight=None) -> list:
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ZEBRA]),
        ("GRID", (0, 0), (-1, -1), 0.25, GRID),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    for index in highlight or ():
        style.append(("BACKGROUND", (0, index), (-1, index), GAP_BG))
        style.append(("FONTNAME", (0, index), (-1, index), "Helvetica-Bold"))
    return style


def _grid_section(campaign) -> tuple[list, list[int]]:
    """Page 1 : la grille. Renvoie le flux et les index de lignes à surligner."""
    gaps = []
    rows = [GRID_HEADERS]
    for position, row in enumerate(services.by_day(campaign), start=1):
        slot = row["slot"]
        rows.append([
            str(slot.get_weekday_display()).capitalize(),
            "%s – %s" % (slot.start_time.strftime("%H:%M"), slot.end_time.strftime("%H:%M")),
            slot.label or "—",
            str(slot.capacity),
            ", ".join(str(item.member.get_full_name()) for item in row["yes"]) or "personne",
            ", ".join(str(item.member.get_full_name()) for item in row["maybe"]) or "—",
            "couvert" if row["covered"] else "à pourvoir",
        ])
        if not row["covered"]:
            gaps.append(position)
    if len(rows) == 1:
        rows.append(["—", "—", "Aucun créneau dans cette campagne", "—", "—", "—", "—"])
    return rows, gaps


def _member_section(campaign) -> list:
    """Page 2 : qui a répondu quoi, et sur quels créneaux."""
    from plannings.models import Availability

    answers = (Availability.objects.filter(campaign=campaign)
               .select_related("member", "slot").order_by("member__last_name", "member__first_name"))
    per_member: dict[int, dict] = {}
    for item in answers:
        bucket = per_member.setdefault(item.member_id, {
            "member": item.member, "yes": 0, "maybe": 0, "no": 0, "slots": []})
        bucket[item.choice] += 1
        if item.choice in ("yes", "maybe"):
            bucket["slots"].append(str(item.slot))
    rows = [MEMBER_HEADERS]
    for bucket in per_member.values():
        rows.append([
            bucket["member"].get_full_name() or bucket["member"].email,
            str(bucket["yes"]),
            str(bucket["maybe"]),
            str(bucket["no"]),
            "; ".join(bucket["slots"]) or "—",
        ])
    if len(rows) == 1:
        rows.append(["Aucune réponse enregistrée", "—", "—", "—", "—"])
    return rows


def campaign_pdf(campaign) -> HttpResponse:
    """Le PDF complet d'une campagne : grille à afficher puis synthèse par membre."""
    buffer = io.BytesIO()
    nom, full = brand_lines()
    stats = services.campaign_stats(campaign)
    generated = timezone.localtime().strftime("%d/%m/%Y %H:%M")
    page_width = landscape(A4)[0]

    def on_page(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(15 * mm, A4[1] - 10 * mm, full)
        canvas.drawRightString(page_width - 15 * mm, A4[1] - 10 * mm,
                               "Planning « %s » — généré le %s" % (campaign.label, generated))
        canvas.drawString(15 * mm, 10 * mm, nom)
        canvas.drawRightString(page_width - 15 * mm, 10 * mm, "Page %d" % doc.page)
        canvas.setStrokeColor(GRID)
        canvas.line(15 * mm, 13 * mm, page_width - 15 * mm, 13 * mm)
        canvas.restoreState()

    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), leftMargin=15 * mm, rightMargin=15 * mm,
                            topMargin=18 * mm, bottomMargin=16 * mm,
                            title="Planning %s" % campaign.label, author=nom)
    styles = getSampleStyleSheet()
    heading = ParagraphStyle("h", parent=styles["Title"], fontSize=15, spaceAfter=4)
    sub = ParagraphStyle("s", parent=styles["Normal"], fontSize=9, textColor=MUTED)

    grid_rows, gaps = _grid_section(campaign)
    story = [
        Paragraph("Planning de la salle — %s" % campaign.label, heading),
        Paragraph(
            "%s · réponses du %s au %s · %d %% de réponses · %d créneau(x) sans gérant"
            % (campaign.get_week_display(), campaign.start_date.strftime("%d/%m/%Y"),
               campaign.end_date.strftime("%d/%m/%Y"), stats["reponse_pct"], stats["gaps"]),
            sub,
        ),
        Spacer(1, 8),
    ]
    grid = Table(grid_rows, colWidths=GRID_WIDTHS, repeatRows=1)
    grid.setStyle(TableStyle(_table_style(len(grid_rows), highlight=gaps)))
    story.append(grid)
    if gaps:
        story.append(Spacer(1, 6))
        story.append(Paragraph("Les lignes orangées sont les créneaux sans gérant : "
                               "à pourvoir avant publication.", sub))

    story.append(PageBreak())
    story.append(Paragraph("Synthèse par membre", heading))
    story.append(Paragraph(
        "%d membre(s) ont répondu sur %d attendu(s). Utilisez cette page pour relancer "
        "nominativement les absents." % (stats["answered_members"], stats["members"]), sub))
    story.append(Spacer(1, 8))
    member_rows = _member_section(campaign)
    members = Table(member_rows, colWidths=MEMBER_WIDTHS, repeatRows=1)
    members.setStyle(TableStyle(_table_style(len(member_rows))))
    story.append(members)

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    buffer.seek(0)
    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = 'attachment; filename="planning-%d.pdf"' % campaign.pk
    return response
