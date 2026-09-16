"""Jeu d'icônes SVG inline (aucune dépendance externe, aucune police d'icônes)."""
from __future__ import annotations

PATHS = {
    "home": '<path d="M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/>',
    "folder": '<path d="M3 6a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "coins": '<circle cx="9" cy="9" r="5"/><path d="M15.5 5.5a5 5 0 1 1 0 9"/><path d="M9 7v4"/>',
    "calendar": '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>',
    "broom": '<path d="M14 3l7 7-4 4-7-7z"/><path d="M10 10 4 21l7-4"/>',
    "mail": '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6"/>',
    "users": '<circle cx="9" cy="8" r="3.2"/><path d="M3 20c0-3.3 2.7-5.5 6-5.5s6 2.2 6 5.5"/><path d="M16 5.5a3.2 3.2 0 0 1 0 6.4M17 14.6c2.4.5 4 2.4 4 5.4"/>',
    "shield": '<path d="M12 3l7 3v6c0 4.4-3 8-7 9-4-1-7-4.6-7-9V6z"/><path d="m9 12 2 2 4-4"/>',
    "sliders": '<path d="M4 7h10M18 7h2M4 12h4M12 12h8M4 17h12M20 17h0"/><circle cx="16" cy="7" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="18" cy="17" r="2"/>',
    "list": '<path d="M8 6h13M8 12h13M8 18h13M3.5 6h.01M3.5 12h.01M3.5 18h.01"/>',
    "save": '<path d="M5 3h11l3 3v15H5z"/><path d="M8 3v6h7V3M8 21v-6h8v6"/>',
    "bell": '<path d="M6 9a6 6 0 1 1 12 0c0 4 1.5 5.5 1.5 5.5h-15S6 13 6 9z"/><path d="M10 19a2 2 0 0 0 4 0"/>',
    "search": '<circle cx="11" cy="11" r="6"/><path d="m20 20-4.5-4.5"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "download": '<path d="M12 4v11m0 0 4-4m-4 4-4-4M4 20h16"/>',
    "upload": '<path d="M12 20V9m0 0 4 4m-4-4-4 4M4 4h16"/>',
    "trash": '<path d="M4 7h16M9 7V4h6v3M6 7l1 14h10l1-14"/>',
    "edit": '<path d="M4 20h4L20 8l-4-4L4 16z"/>',
    "check": '<path d="m5 13 4 4L19 7"/>',
    "cross": '<path d="M6 6l12 12M18 6 6 18"/>',
    "lock": '<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
    "eye": '<path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6-10-6-10-6z"/><circle cx="12" cy="12" r="2.5"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5 19 19M19 5l-1.5 1.5M6.5 17.5 5 19"/>',
    "moon": '<path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z"/>',
    "logout": '<path d="M15 4h4a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1h-4"/><path d="M10 8 6 12l4 4M6 12h10"/>',
    "print": '<path d="M7 9V4h10v5"/><rect x="4" y="9" width="16" height="7" rx="1"/><path d="M7 16h10v4H7z"/>',
    "filter": '<path d="M4 5h16l-6 7v7l-4-2v-5z"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
    "warning": '<path d="M12 4 2.5 20h19z"/><path d="M12 10v4M12 17h.01"/>',
    "refresh": '<path d="M20 12a8 8 0 1 1-2.5-5.8"/><path d="M20 4v5h-5"/>',
    "file": '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4"/>',
    "image": '<rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="9" cy="10" r="1.6"/><path d="m4 18 5-5 4 4 3-2 4 4"/>',
    "chart": '<path d="M4 20V6M4 20h16"/><rect x="7" y="12" width="3" height="6"/><rect x="12" y="8" width="3" height="10"/><rect x="17" y="14" width="3" height="4"/>',
    "key": '<circle cx="8" cy="12" r="4"/><path d="M12 12h9l-2 2-2-2-2 2-2-2"/>',
    "send": '<path d="M4 12 20 4l-7 16-2-6z"/>',
    "user": '<circle cx="12" cy="8" r="4"/><path d="M4 20c0-4 3.6-6 8-6s8 2 8 6"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "wifi-off": '<path d="M3 3l18 18M8.5 15.5a5 5 0 0 1 7 0M5 12a10 10 0 0 1 4-2.5M19 12a10 10 0 0 0-6-2.9M12 19h.01"/>',
    "grid": '<rect x="4" y="4" width="7" height="7"/><rect x="13" y="4" width="7" height="7"/><rect x="4" y="13" width="7" height="7"/><rect x="13" y="13" width="7" height="7"/>',
    "copy": '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 5H6a2 2 0 0 0-2 2v10"/>',
}


def svg_icon(name: str, size: int = 16, cls: str = "icon") -> str:
    body = PATHS.get(name, PATHS["info"])
    return (
        '<svg class="%s" width="%d" height="%d" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.7" stroke-linecap="round" '
        'stroke-linejoin="round" aria-hidden="true">%s</svg>' % (cls, size, size, body)
    )
