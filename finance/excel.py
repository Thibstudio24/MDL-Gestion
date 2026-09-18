"""Génération du classeur Excel du bilan mensuel (openpyxl, zéro dépendance externe)."""
from __future__ import annotations

import io
from datetime import date
from decimal import Decimal

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from finance.models import Account, AccountOpening, CashCount, Category, Entry, MonthLock

NUMBER = '#,##0.00 "€"'
DATE_FORMAT = "DD/MM/YYYY"
HEADER_FILL = PatternFill("solid", fgColor="33556E")
HEADER_FONT = Font(color="FFFFFF", bold=True, size=10)
TOTAL_FONT = Font(bold=True, size=10)
TITLE_FONT = Font(bold=True, size=14, color="33556E")
THIN = Side(style="thin", color="D6D6D6")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
LOCKED_FILL = PatternFill("solid", fgColor="FDF3E7")


def _header_row(sheet, row: int, labels: list[str], widths: list[int] | None = None) -> None:
    for index, label in enumerate(labels, start=1):
        cell = sheet.cell(row=row, column=index, value=label)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = BOX
    sheet.freeze_panes = sheet.cell(row=row + 1, column=1)
    if widths:
        for index, width in enumerate(widths, start=1):
            sheet.column_dimensions[get_column_letter(index)].width = width


def _write(sheet, row: int, values: list, number_columns: tuple[int, ...] = ()) -> None:
    for index, value in enumerate(values, start=1):
        cell = sheet.cell(row=row, column=index, value=value)
        cell.border = BOX
        if index in number_columns:
            cell.number_format = NUMBER
        if isinstance(value, date):
            cell.number_format = DATE_FORMAT


def _total(sheet, row: int, label: str, expense: Decimal, income: Decimal, start_col: int = 8) -> None:
    sheet.cell(row=row, column=1, value=label).font = TOTAL_FONT
    cell_expense = sheet.cell(row=row, column=start_col, value=float(expense))
    cell_income = sheet.cell(row=row, column=start_col + 1, value=float(income))
    for cell in (cell_expense, cell_income):
        cell.number_format = NUMBER
        cell.font = TOTAL_FONT


def _sheet_summary(workbook: Workbook, year, months: list[dict], up_to: date) -> None:
    sheet = workbook.active
    sheet.title = "Synthèse"
    sheet["A1"] = "Bilan mensuel — %s" % year.label
    sheet["A1"].font = TITLE_FONT
    sheet["A2"] = "Généré le %s — arrêté au %s" % (date.today().strftime("%d/%m/%Y"), up_to.strftime("%d/%m/%Y"))
    sheet["A2"].font = Font(italic=True, size=9, color="666666")
    _header_row(sheet, 4, ["Mois", "Solde initial", "Recettes", "Dépenses", "Solde final", "Écritures", "Clôturé"],
                [16, 16, 14, 14, 16, 12, 12])
    row = 5
    running = Decimal("0.00")
    accounts = Account.objects.filter(active=True)
    for account in accounts:
        opening = AccountOpening.objects.filter(year=year, account=account).first()
        running += opening.amount if opening else Decimal("0.00")
    for item in months:
        entries = Entry.objects.filter(year=year, day__gte=item["start"], day__lte=item["end"])
        expenses = sum((e.amount for e in entries if e.kind == "D"), Decimal("0.00"))
        incomes = sum((e.amount for e in entries if e.kind == "R"), Decimal("0.00"))
        initial = running
        running = running + incomes - expenses
        locked = MonthLock.objects.filter(year=year, month=item["month"], year_number=item["year"]).exists()
        _write(sheet, row, ["%02d/%d" % (item["month"], item["year"]), float(initial), float(incomes),
                            float(expenses), float(running), entries.count(), "oui" if locked else "non"],
               number_columns=(2, 3, 4, 5))
        if locked:
            for column in range(1, 8):
                sheet.cell(row=row, column=column).fill = LOCKED_FILL
        row += 1
    _write(sheet, row, ["Total", None, None, None, float(running), None, None], number_columns=(5,))
    for column in range(1, 8):
        sheet.cell(row=row, column=column).font = TOTAL_FONT
    row += 2
    sheet.cell(row=row, column=1, value="Comptes").font = TOTAL_FONT
    row += 1
    _header_row(sheet, row, ["Compte", "Solde d'ouverture", "Mouvements", "Solde final"])
    row += 1
    for account in accounts:
        from finance.services import balance_for_account

        data = balance_for_account(year, account, up_to)
        _write(sheet, row, [account.name, float(data["opening"]), float(data["movements"]), float(data["total"])],
               number_columns=(2, 3, 4))
        row += 1


def _sheet_month(workbook: Workbook, year, item: dict) -> None:
    title = "%02d-%d" % (item["month"], item["year"])
    sheet = workbook.create_sheet("Mois %s" % title)
    entries = list(Entry.objects.filter(year=year, day__gte=item["start"], day__lte=item["end"])
                   .select_related("account", "category", "subcategory")
                   .order_by("day", "id"))
    locked = MonthLock.objects.filter(year=year, month=item["month"], year_number=item["year"]).first()
    sheet["A1"] = "Grand livre — %s" % title
    sheet["A1"].font = TITLE_FONT
    sheet["A2"] = ("Mois clôturé le %s par %s — verrouillé" % (locked.locked_at.strftime("%d/%m/%Y"),
                   locked.locked_by or "—")) if locked else "Mois ouvert"
    sheet["A2"].font = Font(italic=True, size=9, color="666666")
    _header_row(sheet, 4, ["N°", "Date", "Pièce", "Libellé", "Compte", "Catégorie", "Sous-catégorie",
                           "Mode", "Tiers", "Dépense", "Recette"],
                [7, 12, 14, 42, 18, 20, 20, 14, 22, 13, 13])
    row = 5
    total_expenses = Decimal("0.00")
    total_incomes = Decimal("0.00")
    subtotal_by_category: dict[str, dict[str, Decimal]] = {}
    for index, entry in enumerate(entries, start=1):
        expense = float(entry.amount) if entry.kind == "D" else None
        income = float(entry.amount) if entry.kind == "R" else None
        if entry.kind == "D":
            total_expenses += entry.amount
        elif entry.kind == "R":
            total_incomes += entry.amount
        _write(sheet, row, [index, entry.day, entry.reference, entry.title, entry.account.name,
                            entry.category.label if entry.category_id else "",
                            entry.subcategory.label if entry.subcategory_id else "",
                            entry.get_mode_display() if entry.mode else "", entry.third_party,
                            expense, income], number_columns=(10, 11))
        if entry.category_id and entry.kind in ("D", "R"):
            bucket = subtotal_by_category.setdefault(entry.category.label,
                                                     {"D": Decimal("0.00"), "R": Decimal("0.00")})
            bucket[entry.kind] += entry.amount
        row += 1
    _total(sheet, row, "Total du mois", total_expenses, total_incomes, start_col=10)
    row += 2
    sheet.cell(row=row, column=1, value="Sous-totaux par catégorie").font = TOTAL_FONT
    row += 1
    _header_row(sheet, row, ["Catégorie", "Dépenses", "Recettes"])
    row += 1
    for label in sorted(subtotal_by_category):
        bucket = subtotal_by_category[label]
        _write(sheet, row, [label, float(bucket["D"]) or None, float(bucket["R"]) or None],
               number_columns=(2, 3))
        row += 1
    sheet.auto_filter.ref = "A4:K%d" % (4 + len(entries))


def _sheet_categories(workbook: Workbook, year, months: list[dict]) -> None:
    sheet = workbook.create_sheet("Catégories")
    sheet["A1"] = "Croisement catégorie × mois"
    sheet["A1"].font = TITLE_FONT
    categories = list(Category.objects.filter(active=True).order_by("kind", "order", "label"))
    labels = ["Catégorie", "Sens"] + ["%02d/%d" % (item["month"], item["year"]) for item in months] + ["Total"]
    _header_row(sheet, 3, labels, [26, 10] + [13] * len(months) + [14])
    row = 4
    for category in categories:
        values = [category.label, "Dépense" if category.kind == "D" else "Recette"]
        total = Decimal("0.00")
        for item in months:
            amount = (Entry.objects.filter(year=year, category=category, day__gte=item["start"],
                                           day__lte=item["end"])
                      .aggregate(total=__import__("django").db.models.Sum("amount"))["total"] or Decimal("0.00"))
            total += amount
            values.append(float(amount) or None)
        values.append(float(total))
        _write(sheet, row, values, number_columns=tuple(range(3, len(values) + 1)))
        row += 1


def _sheet_reconciliation(workbook: Workbook, year, months: list[dict], up_to: date) -> None:
    sheet = workbook.create_sheet("Rapprochement")
    sheet["A1"] = "Rapprochement bancaire et comptages de caisse"
    sheet["A1"].font = TITLE_FONT
    _header_row(sheet, 3, ["Compte", "Solde d'ouverture", "Notre solde", "Solde relevé", "Écart", "Statut"],
                [26, 18, 16, 16, 14, 16])
    row = 4
    for account in Account.objects.filter(active=True, is_safe=False):
        from finance.services import balance_for_account

        data = balance_for_account(year, account, up_to)
        _write(sheet, row, [account.name, float(data["opening"]), float(data["total"]), None, None,
                            "à rapprocher"], number_columns=(2, 3, 4, 5))
        row += 1
    row += 2
    sheet.cell(row=row, column=1, value="Comptages de caisse").font = TOTAL_FONT
    row += 1
    _header_row(sheet, row, ["Date", "Compte", "Théorique", "Compté", "Écart", "Motif", "Ajustement"])
    row += 1
    for count in CashCount.objects.filter(year=year, day__lte=up_to).select_related("account", "adjustment"):
        _write(sheet, row, [count.day, count.account.name, float(count.expected), float(count.counted),
                            float(count.delta), count.reason,
                            ("oui (%s)" % count.adjustment.get_kind_display()) if count.adjustment_id else "non"],
               number_columns=(3, 4, 5))
        row += 1


def build_workbook(year, months: list[dict], up_to: date) -> bytes:
    """Construit le classeur complet et le renvoie en octets (xlsx)."""
    workbook = Workbook()
    _sheet_summary(workbook, year, months, up_to)
    for item in months:
        _sheet_month(workbook, year, item)
    _sheet_categories(workbook, year, months)
    _sheet_reconciliation(workbook, year, months, up_to)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
