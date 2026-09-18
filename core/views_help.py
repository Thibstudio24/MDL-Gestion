"""Mode d'emploi en ligne (/aide/) : sommaire cliquable, pages imprimables."""
from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from core.help_content import CHECKLIST_EMAIL, FAQ, GLOSSARY, SECTIONS
from core.rich import render as render_markdown


@login_required
def index(request):
    return render(request, "core/help/index.html", {
        "sections": [{"id": sid, "title": title} for sid, title, _body in SECTIONS],
        "page_title": "Mode d'emploi",
    })


@login_required
def section(request, sid: str):
    match = next((item for item in SECTIONS if item[0] == sid), None)
    if match is None:
        return render(request, "core/404.html", {"page_title": "Page introuvable"}, status=404)
    identifier, title, body = match
    if identifier == "24":
        return faq(request)
    if identifier == "25":
        return glossary(request)
    index = next(i for i, item in enumerate(SECTIONS) if item[0] == identifier)
    return render(request, "core/help/section.html", {
        "id": identifier,
        "title": title,
        "html": render_markdown(body),
        "previous": SECTIONS[index - 1] if index else None,
        "next": SECTIONS[index + 1] if index + 1 < len(SECTIONS) else None,
        "sections": [{"id": sid, "title": t} for sid, t, _b in SECTIONS],
        "page_title": "%s %s" % (identifier, title),
    })


@login_required
def faq(request):
    return render(request, "core/help/faq.html", {
        "faq": [{"question": q, "html": render_markdown(a)} for q, a in FAQ],
        "sections": [{"id": sid, "title": title} for sid, title, _body in SECTIONS],
        "page_title": "FAQ",
    })


@login_required
def glossary(request):
    return render(request, "core/help/glossary.html", {
        "glossary": GLOSSARY,
        "sections": [{"id": sid, "title": title} for sid, title, _body in SECTIONS],
        "page_title": "Glossaire",
    })


@login_required
def checklist(request):
    return render(request, "core/help/checklist.html", {
        "email": CHECKLIST_EMAIL,
        "sections": [{"id": sid, "title": title} for sid, title, _body in SECTIONS],
        "page_title": "Check-list de rentrée",
    })
